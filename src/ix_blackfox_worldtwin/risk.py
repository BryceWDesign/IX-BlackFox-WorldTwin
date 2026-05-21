"""Risk scoring for IX-BlackFox-WorldTwin.

Risk scoring converts bounded branch outcomes into reviewable caution, denial,
or quarantine recommendations. It does not authorize action. It gives later
prediction, receipt, policy, reality-delta, and handoff layers a deterministic
way to identify the highest-risk modeled branch.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.branching import BranchComparison, BranchSimulationResult

RISK_SCHEMA_VERSION = "risk-scoring-v1"
RISK_ID_DIGEST_LENGTH = 16


class RiskSeverity(StrEnum):
    """Severity tiers for deterministic WorldTwin risk scoring."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RiskRecommendation(StrEnum):
    """Review recommendation derived from a risk score."""

    ACCEPT = "accept"
    CAUTION = "caution"
    DENY = "deny"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class RiskFactor:
    """A single scored factor contributing to a branch risk profile."""

    factor_id: str
    target: str
    observed_value: float
    normalized_value: float
    weight: float
    severity: RiskSeverity
    rationale: str
    tags: tuple[str, ...] = ()
    schema_version: str = RISK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a risk factor."""

        object.__setattr__(self, "factor_id", _require_non_empty(self.factor_id, "factor id"))
        object.__setattr__(self, "target", _require_non_empty(self.target, "risk target"))
        object.__setattr__(
            self,
            "observed_value",
            _require_finite_float(self.observed_value, "risk observed value"),
        )
        object.__setattr__(
            self,
            "normalized_value",
            _require_unit_interval(self.normalized_value, "risk normalized value"),
        )
        object.__setattr__(self, "weight", _require_positive_float(self.weight, "risk weight"))
        object.__setattr__(self, "rationale", _require_non_empty(self.rationale, "rationale"))
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "risk tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "risk schema version"),
        )

    @property
    def weighted_contribution(self) -> float:
        """Return the weighted contribution of this factor."""

        return self.normalized_value * self.weight

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "factor_id": self.factor_id,
            "normalized_value": self.normalized_value,
            "observed_value": self.observed_value,
            "rationale": self.rationale,
            "schema_version": self.schema_version,
            "severity": self.severity.value,
            "tags": list(self.tags),
            "target": self.target,
            "weight": self.weight,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this risk factor."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class RiskProfile:
    """A deterministic risk profile for one simulated branch."""

    profile_id: str
    scenario_id: str
    branch_id: str
    simulation_id: str
    aggregate_score: float
    severity: RiskSeverity
    recommendation: RiskRecommendation
    factors: tuple[RiskFactor, ...]
    created_at: datetime
    created_by: str
    schema_version: str = RISK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a risk profile."""

        if not self.factors:
            raise ValueError("risk profile requires at least one factor")

        object.__setattr__(self, "profile_id", _require_non_empty(self.profile_id, "profile id"))
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(self, "branch_id", _require_non_empty(self.branch_id, "branch id"))
        object.__setattr__(
            self,
            "simulation_id",
            _require_non_empty(self.simulation_id, "simulation id"),
        )
        object.__setattr__(
            self,
            "aggregate_score",
            _require_unit_interval(self.aggregate_score, "aggregate risk score"),
        )
        object.__setattr__(self, "factors", _normalize_risk_factors(self.factors))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "risk profile created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "risk schema version"),
        )

    @property
    def blocks_execution_review(self) -> bool:
        """Return True when the profile recommends denial or quarantine."""

        return self.recommendation in {
            RiskRecommendation.DENY,
            RiskRecommendation.QUARANTINE,
        }

    @property
    def requires_human_caution(self) -> bool:
        """Return True when the profile recommends caution."""

        return self.recommendation is RiskRecommendation.CAUTION

    def highest_factor_severity(self) -> RiskSeverity:
        """Return the highest factor severity in this profile."""

        return max((factor.severity for factor in self.factors), key=_severity_rank)

    def factor_targets(self) -> tuple[str, ...]:
        """Return scored factor targets in deterministic order."""

        return tuple(factor.target for factor in self.factors)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "aggregate_score": self.aggregate_score,
            "branch_id": self.branch_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "factors": [factor.canonical_payload() for factor in self.factors],
            "profile_id": self.profile_id,
            "recommendation": self.recommendation.value,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "severity": self.severity.value,
            "simulation_id": self.simulation_id,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this risk profile."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class RiskComparison:
    """Aggregate risk comparison across branch profiles."""

    comparison_id: str
    scenario_id: str
    profiles: tuple[RiskProfile, ...]
    created_at: datetime
    created_by: str
    schema_version: str = RISK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a risk comparison."""

        if not self.profiles:
            raise ValueError("risk comparison requires at least one profile")

        scenario_ids = {profile.scenario_id for profile in self.profiles}
        if len(scenario_ids) != 1:
            raise ValueError("risk comparison profiles must share one scenario id")
        if self.scenario_id not in scenario_ids:
            raise ValueError("risk comparison scenario_id must match profile scenario id")

        profile_ids = [profile.profile_id for profile in self.profiles]
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("risk comparison contains duplicate profile ids")

        object.__setattr__(
            self,
            "comparison_id",
            _require_non_empty(self.comparison_id, "risk comparison id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "profiles",
            tuple(sorted(self.profiles, key=lambda profile: profile.profile_id)),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "risk comparison created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "risk schema version"),
        )

    def ranked_profiles(self) -> tuple[RiskProfile, ...]:
        """Return profiles ranked from highest risk to lowest risk."""

        return tuple(
            sorted(
                self.profiles,
                key=lambda profile: (profile.aggregate_score, profile.profile_id),
                reverse=True,
            )
        )

    def highest_risk_profile(self) -> RiskProfile:
        """Return the highest-risk profile."""

        return self.ranked_profiles()[0]

    def lowest_risk_profile(self) -> RiskProfile:
        """Return the lowest-risk profile."""

        return self.ranked_profiles()[-1]

    def branch_score_table(self) -> dict[str, float]:
        """Return branch ids mapped to aggregate risk score."""

        return {
            profile.branch_id: profile.aggregate_score for profile in self.ranked_profiles()
        }

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "comparison_id": self.comparison_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "profile_fingerprints": [profile.fingerprint() for profile in self.profiles],
            "profile_ids": [profile.profile_id for profile in self.profiles],
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this risk comparison."""

        return _stable_sha256(self.canonical_payload())


def score_branch_risk(
    *,
    result: BranchSimulationResult,
    target_weights: Mapping[str, float],
    created_at: datetime,
    created_by: str,
    caution_threshold: float = 0.40,
    deny_threshold: float = 0.70,
    quarantine_threshold: float = 0.90,
    profile_id: str | None = None,
) -> RiskProfile:
    """Score one simulated branch against weighted final-state targets."""

    normalized_target_weights = _normalize_target_weights(target_weights)
    normalized_created_at = _require_aware_utc_datetime(created_at, "risk profile created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    _validate_thresholds(
        caution_threshold=caution_threshold,
        deny_threshold=deny_threshold,
        quarantine_threshold=quarantine_threshold,
    )

    factors = tuple(
        create_risk_factor(
            target=target,
            observed_value=result.final_value(target),
            weight=weight,
            rationale=f"Weighted risk contribution from final simulated target '{target}'.",
        )
        for target, weight in normalized_target_weights.items()
    )
    aggregate_score = _aggregate_factor_score(factors)
    severity = classify_risk_severity(
        score=aggregate_score,
        caution_threshold=caution_threshold,
        deny_threshold=deny_threshold,
        quarantine_threshold=quarantine_threshold,
    )
    recommendation = classify_risk_recommendation(
        score=aggregate_score,
        caution_threshold=caution_threshold,
        deny_threshold=deny_threshold,
        quarantine_threshold=quarantine_threshold,
    )
    resolved_profile_id = profile_id or make_risk_profile_id(
        scenario_id=result.scenario_id,
        branch_id=result.branch_id,
        simulation_id=result.simulation.simulation_id,
        aggregate_score=aggregate_score,
        severity=severity,
        recommendation=recommendation,
        factors=factors,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
    )

    return RiskProfile(
        profile_id=resolved_profile_id,
        scenario_id=result.scenario_id,
        branch_id=result.branch_id,
        simulation_id=result.simulation.simulation_id,
        aggregate_score=aggregate_score,
        severity=severity,
        recommendation=recommendation,
        factors=factors,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
    )


def compare_branch_risks(
    *,
    comparison: BranchComparison,
    target_weights: Mapping[str, float],
    created_at: datetime,
    created_by: str,
    comparison_id: str | None = None,
) -> RiskComparison:
    """Score and compare every branch inside a branch comparison."""

    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "risk comparison created_at",
    )
    normalized_created_by = _require_non_empty(created_by, "created by")
    profiles = tuple(
        score_branch_risk(
            result=result,
            target_weights=target_weights,
            created_at=normalized_created_at,
            created_by=normalized_created_by,
        )
        for result in comparison.results
    )
    resolved_comparison_id = comparison_id or make_risk_comparison_id(
        scenario_id=comparison.scenario_id,
        profiles=profiles,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
    )

    return RiskComparison(
        comparison_id=resolved_comparison_id,
        scenario_id=comparison.scenario_id,
        profiles=profiles,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
    )


def create_risk_factor(
    *,
    target: str,
    observed_value: float,
    weight: float,
    rationale: str,
    factor_id: str | None = None,
    tags: tuple[str, ...] = (),
) -> RiskFactor:
    """Create a risk factor from one final simulated target."""

    normalized_target = _require_non_empty(target, "risk target")
    normalized_observed_value = _require_finite_float(observed_value, "risk observed value")
    normalized_value = _normalize_observed_risk_value(normalized_observed_value)
    normalized_weight = _require_positive_float(weight, "risk weight")
    normalized_rationale = _require_non_empty(rationale, "rationale")
    normalized_tags = _normalize_unique_text_tuple(tags, "risk tag")
    severity = _factor_severity(normalized_value)
    resolved_factor_id = factor_id or make_risk_factor_id(
        target=normalized_target,
        observed_value=normalized_observed_value,
        normalized_value=normalized_value,
        weight=normalized_weight,
        severity=severity,
        rationale=normalized_rationale,
        tags=normalized_tags,
    )

    return RiskFactor(
        factor_id=resolved_factor_id,
        target=normalized_target,
        observed_value=normalized_observed_value,
        normalized_value=normalized_value,
        weight=normalized_weight,
        severity=severity,
        rationale=normalized_rationale,
        tags=normalized_tags,
    )


def classify_risk_severity(
    *,
    score: float,
    caution_threshold: float = 0.40,
    deny_threshold: float = 0.70,
    quarantine_threshold: float = 0.90,
) -> RiskSeverity:
    """Classify aggregate risk score into severity."""

    normalized_score = _require_unit_interval(score, "risk score")
    _validate_thresholds(
        caution_threshold=caution_threshold,
        deny_threshold=deny_threshold,
        quarantine_threshold=quarantine_threshold,
    )

    if normalized_score >= quarantine_threshold:
        return RiskSeverity.CRITICAL
    if normalized_score >= deny_threshold:
        return RiskSeverity.ERROR
    if normalized_score >= caution_threshold:
        return RiskSeverity.WARNING
    return RiskSeverity.INFO


def classify_risk_recommendation(
    *,
    score: float,
    caution_threshold: float = 0.40,
    deny_threshold: float = 0.70,
    quarantine_threshold: float = 0.90,
) -> RiskRecommendation:
    """Classify aggregate risk score into a review recommendation."""

    severity = classify_risk_severity(
        score=score,
        caution_threshold=caution_threshold,
        deny_threshold=deny_threshold,
        quarantine_threshold=quarantine_threshold,
    )

    if severity is RiskSeverity.CRITICAL:
        return RiskRecommendation.QUARANTINE
    if severity is RiskSeverity.ERROR:
        return RiskRecommendation.DENY
    if severity is RiskSeverity.WARNING:
        return RiskRecommendation.CAUTION
    return RiskRecommendation.ACCEPT


def make_risk_factor_id(
    *,
    target: str,
    observed_value: float,
    normalized_value: float,
    weight: float,
    severity: RiskSeverity,
    rationale: str,
    tags: tuple[str, ...] = (),
) -> str:
    """Create a deterministic risk-factor id."""

    payload = {
        "normalized_value": _require_unit_interval(normalized_value, "risk normalized value"),
        "observed_value": _require_finite_float(observed_value, "risk observed value"),
        "rationale": _require_non_empty(rationale, "rationale"),
        "schema_version": RISK_SCHEMA_VERSION,
        "severity": severity.value,
        "tags": list(_normalize_unique_text_tuple(tags, "risk tag")),
        "target": _require_non_empty(target, "risk target"),
        "weight": _require_positive_float(weight, "risk weight"),
    }
    digest = _stable_sha256(payload)[:RISK_ID_DIGEST_LENGTH]
    return f"risk-factor-{digest}"


def make_risk_profile_id(
    *,
    scenario_id: str,
    branch_id: str,
    simulation_id: str,
    aggregate_score: float,
    severity: RiskSeverity,
    recommendation: RiskRecommendation,
    factors: tuple[RiskFactor, ...],
    created_at: datetime,
    created_by: str,
) -> str:
    """Create a deterministic risk-profile id."""

    payload = {
        "aggregate_score": _require_unit_interval(aggregate_score, "aggregate risk score"),
        "branch_id": _require_non_empty(branch_id, "branch id"),
        "created_at": _require_aware_utc_datetime(
            created_at,
            "risk profile created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "factors": [factor.canonical_payload() for factor in _normalize_risk_factors(factors)],
        "recommendation": recommendation.value,
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": RISK_SCHEMA_VERSION,
        "severity": severity.value,
        "simulation_id": _require_non_empty(simulation_id, "simulation id"),
    }
    digest = _stable_sha256(payload)[:RISK_ID_DIGEST_LENGTH]
    return f"risk-profile-{digest}"


def make_risk_comparison_id(
    *,
    scenario_id: str,
    profiles: tuple[RiskProfile, ...],
    created_at: datetime,
    created_by: str,
) -> str:
    """Create a deterministic risk-comparison id."""

    if not profiles:
        raise ValueError("risk comparison id requires at least one profile")

    payload = {
        "created_at": _require_aware_utc_datetime(
            created_at,
            "risk comparison created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "profile_fingerprints": [
            profile.fingerprint() for profile in sorted(profiles, key=lambda item: item.profile_id)
        ],
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": RISK_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:RISK_ID_DIGEST_LENGTH]
    return f"risk-comparison-{digest}"


def _aggregate_factor_score(factors: tuple[RiskFactor, ...]) -> float:
    normalized_factors = _normalize_risk_factors(factors)
    total_weight = sum(factor.weight for factor in normalized_factors)
    weighted_sum = sum(factor.weighted_contribution for factor in normalized_factors)
    return min(1.0, weighted_sum / total_weight)


def _normalize_observed_risk_value(value: float) -> float:
    finite_value = _require_finite_float(value, "risk observed value")
    return min(1.0, max(0.0, finite_value))


def _factor_severity(normalized_value: float) -> RiskSeverity:
    return classify_risk_severity(score=normalized_value)


def _normalize_target_weights(target_weights: Mapping[str, float]) -> dict[str, float]:
    if not target_weights:
        raise ValueError("risk scoring requires at least one target weight")

    normalized: dict[str, float] = {}
    for target, weight in target_weights.items():
        normalized_target = _require_non_empty(target, "risk target")
        if normalized_target in normalized:
            raise ValueError(f"duplicate risk target: {normalized_target}")
        normalized[normalized_target] = _require_positive_float(weight, "risk weight")

    return dict(sorted(normalized.items()))


def _normalize_risk_factors(factors: tuple[RiskFactor, ...]) -> tuple[RiskFactor, ...]:
    if not factors:
        raise ValueError("risk profile requires at least one factor")

    seen_factor_ids: set[str] = set()
    seen_targets: set[str] = set()
    normalized_factors: list[RiskFactor] = []

    for factor in factors:
        if factor.factor_id in seen_factor_ids:
            raise ValueError(f"duplicate risk factor id: {factor.factor_id}")
        if factor.target in seen_targets:
            raise ValueError(f"duplicate risk target: {factor.target}")
        seen_factor_ids.add(factor.factor_id)
        seen_targets.add(factor.target)
        normalized_factors.append(factor)

    return tuple(sorted(normalized_factors, key=lambda item: item.factor_id))


def _validate_thresholds(
    *,
    caution_threshold: float,
    deny_threshold: float,
    quarantine_threshold: float,
) -> None:
    caution = _require_unit_interval(caution_threshold, "caution threshold")
    deny = _require_unit_interval(deny_threshold, "deny threshold")
    quarantine = _require_unit_interval(quarantine_threshold, "quarantine threshold")

    if not caution < deny < quarantine:
        raise ValueError("risk thresholds must satisfy caution < deny < quarantine")


def _severity_rank(severity: RiskSeverity) -> int:
    ranks = {
        RiskSeverity.INFO: 0,
        RiskSeverity.WARNING: 1,
        RiskSeverity.ERROR: 2,
        RiskSeverity.CRITICAL: 3,
    }
    return ranks[severity]


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized_values = _normalize_text_tuple(values, field_name)
    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError(f"duplicate {field_name}")
    return tuple(sorted(normalized_values))


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        normalized_values.append(_require_non_empty(value, field_name))
    return tuple(normalized_values)


def _require_unit_interval(value: float, field_name: str) -> float:
    normalized_value = _require_finite_float(value, field_name)
    if normalized_value < 0.0 or normalized_value > 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return normalized_value


def _require_positive_float(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    normalized_value = float(value)
    if normalized_value <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized_value


def _require_finite_float(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return float(value)


def _require_non_empty(value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")
    return normalized_value


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()

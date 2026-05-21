"""Prediction result model for IX-BlackFox-WorldTwin.

Prediction results package simulated future-state evidence into a bounded,
reviewable object. A prediction is not authority. It records what was predicted,
which simulation produced it, what confidence was assigned, what risks were
identified, and whether policy review allows it to move forward.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.policy import PolicyDecision, PolicyEvaluation
from ix_blackfox_worldtwin.reproducibility import ReproducibilityManifest
from ix_blackfox_worldtwin.risk import RiskComparison, RiskProfile, RiskRecommendation
from ix_blackfox_worldtwin.simulation import SimulationResult
from ix_blackfox_worldtwin.state import WorldState
from ix_blackfox_worldtwin.uncertainty import ConfidenceAssessment, ConfidenceTier

PREDICTION_SCHEMA_VERSION = "prediction-result-v1"
PREDICTION_ID_DIGEST_LENGTH = 16


class PredictionDisposition(StrEnum):
    """Disposition assigned to a bounded prediction result."""

    ACCEPT = "accept"
    REVIEW = "review"
    CAUTION = "caution"
    DENY = "deny"
    QUARANTINE = "quarantine"


class PredictionSourceKind(StrEnum):
    """Source category for a prediction result."""

    DETERMINISTIC_SIMULATION = "deterministic-simulation"
    BRANCH_RISK_COMPARISON = "branch-risk-comparison"


@dataclass(frozen=True, slots=True)
class PredictionFinding:
    """A reviewable finding attached to a prediction result."""

    code: str
    message: str
    source: str

    def __post_init__(self) -> None:
        """Validate and normalize a prediction finding."""

        object.__setattr__(self, "code", _require_non_empty(self.code, "finding code"))
        object.__setattr__(self, "message", _require_non_empty(self.message, "finding message"))
        object.__setattr__(self, "source", _require_non_empty(self.source, "finding source"))

    def canonical_payload(self) -> dict[str, str]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "code": self.code,
            "message": self.message,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """A bounded prediction result produced from WorldTwin simulation evidence."""

    prediction_id: str
    scenario_id: str
    source_kind: PredictionSourceKind
    final_state: WorldState
    simulation_id: str
    created_at: datetime
    created_by: str
    disposition: PredictionDisposition
    confidence_tier: ConfidenceTier
    findings: tuple[PredictionFinding, ...]
    confidence_assessment_id: str = ""
    risk_profile_id: str = ""
    policy_evaluation_id: str = ""
    reproducibility_manifest_id: str = ""
    schema_version: str = PREDICTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a prediction result."""

        if not self.findings:
            raise ValueError("prediction result requires at least one finding")

        object.__setattr__(
            self,
            "prediction_id",
            _require_non_empty(self.prediction_id, "prediction id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "simulation_id",
            _require_non_empty(self.simulation_id, "simulation id"),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "prediction created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(self, "findings", _normalize_findings(self.findings))
        object.__setattr__(
            self,
            "confidence_assessment_id",
            self.confidence_assessment_id.strip(),
        )
        object.__setattr__(self, "risk_profile_id", self.risk_profile_id.strip())
        object.__setattr__(self, "policy_evaluation_id", self.policy_evaluation_id.strip())
        object.__setattr__(
            self,
            "reproducibility_manifest_id",
            self.reproducibility_manifest_id.strip(),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "prediction schema version"),
        )

    @property
    def final_values(self) -> dict[str, float]:
        """Return predicted final-state values."""

        return self.final_state.to_dimension_map()

    @property
    def blocks_execution_review(self) -> bool:
        """Return True when the prediction should block execution review."""

        return self.disposition in {
            PredictionDisposition.DENY,
            PredictionDisposition.QUARANTINE,
        }

    @property
    def requires_human_review(self) -> bool:
        """Return True when a human should explicitly review the prediction."""

        return self.disposition in {
            PredictionDisposition.REVIEW,
            PredictionDisposition.CAUTION,
            PredictionDisposition.DENY,
            PredictionDisposition.QUARANTINE,
        }

    def finding_codes(self) -> tuple[str, ...]:
        """Return finding codes in deterministic order."""

        return tuple(finding.code for finding in self.findings)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "confidence_assessment_id": self.confidence_assessment_id,
            "confidence_tier": self.confidence_tier.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "disposition": self.disposition.value,
            "final_state_fingerprint": self.final_state.fingerprint(),
            "final_state_id": self.final_state.state_id,
            "findings": [finding.canonical_payload() for finding in self.findings],
            "policy_evaluation_id": self.policy_evaluation_id,
            "prediction_id": self.prediction_id,
            "reproducibility_manifest_id": self.reproducibility_manifest_id,
            "risk_profile_id": self.risk_profile_id,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "simulation_id": self.simulation_id,
            "source_kind": self.source_kind.value,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this prediction result."""

        return _stable_sha256(self.canonical_payload())


def create_prediction_result(
    *,
    simulation: SimulationResult,
    created_at: datetime,
    created_by: str,
    confidence_assessment: ConfidenceAssessment,
    risk_profile: RiskProfile | None = None,
    risk_comparison: RiskComparison | None = None,
    policy_evaluation: PolicyEvaluation | None = None,
    reproducibility_manifest: ReproducibilityManifest | None = None,
    source_kind: PredictionSourceKind = PredictionSourceKind.DETERMINISTIC_SIMULATION,
    prediction_id: str | None = None,
) -> PredictionResult:
    """Create a bounded prediction result from simulation and review artifacts."""

    normalized_created_at = _require_aware_utc_datetime(created_at, "prediction created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    selected_risk_profile = _select_risk_profile(
        simulation=simulation,
        risk_profile=risk_profile,
        risk_comparison=risk_comparison,
    )
    disposition = _derive_disposition(
        confidence_assessment=confidence_assessment,
        risk_profile=selected_risk_profile,
        policy_evaluation=policy_evaluation,
    )
    findings = _build_prediction_findings(
        confidence_assessment=confidence_assessment,
        risk_profile=selected_risk_profile,
        policy_evaluation=policy_evaluation,
        reproducibility_manifest=reproducibility_manifest,
    )
    resolved_prediction_id = prediction_id or make_prediction_id(
        scenario_id=simulation.scenario_id,
        source_kind=source_kind,
        final_state=simulation.final_state,
        simulation_id=simulation.simulation_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        disposition=disposition,
        confidence_tier=confidence_assessment.tier,
        findings=findings,
        confidence_assessment_id=confidence_assessment.assessment_id,
        risk_profile_id="" if selected_risk_profile is None else selected_risk_profile.profile_id,
        policy_evaluation_id=(
            "" if policy_evaluation is None else policy_evaluation.policy_evaluation_id
        ),
        reproducibility_manifest_id=(
            "" if reproducibility_manifest is None else reproducibility_manifest.manifest_id
        ),
    )

    return PredictionResult(
        prediction_id=resolved_prediction_id,
        scenario_id=simulation.scenario_id,
        source_kind=source_kind,
        final_state=simulation.final_state,
        simulation_id=simulation.simulation_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        disposition=disposition,
        confidence_tier=confidence_assessment.tier,
        findings=findings,
        confidence_assessment_id=confidence_assessment.assessment_id,
        risk_profile_id="" if selected_risk_profile is None else selected_risk_profile.profile_id,
        policy_evaluation_id=(
            "" if policy_evaluation is None else policy_evaluation.policy_evaluation_id
        ),
        reproducibility_manifest_id=(
            "" if reproducibility_manifest is None else reproducibility_manifest.manifest_id
        ),
    )


def make_prediction_id(
    *,
    scenario_id: str,
    source_kind: PredictionSourceKind,
    final_state: WorldState,
    simulation_id: str,
    created_at: datetime,
    created_by: str,
    disposition: PredictionDisposition,
    confidence_tier: ConfidenceTier,
    findings: tuple[PredictionFinding, ...],
    confidence_assessment_id: str = "",
    risk_profile_id: str = "",
    policy_evaluation_id: str = "",
    reproducibility_manifest_id: str = "",
) -> str:
    """Create a deterministic prediction-result id."""

    payload = {
        "confidence_assessment_id": confidence_assessment_id.strip(),
        "confidence_tier": confidence_tier.value,
        "created_at": _require_aware_utc_datetime(
            created_at,
            "prediction created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "disposition": disposition.value,
        "final_state_fingerprint": final_state.fingerprint(),
        "final_state_id": final_state.state_id,
        "findings": [
            finding.canonical_payload() for finding in _normalize_findings(findings)
        ],
        "policy_evaluation_id": policy_evaluation_id.strip(),
        "reproducibility_manifest_id": reproducibility_manifest_id.strip(),
        "risk_profile_id": risk_profile_id.strip(),
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "simulation_id": _require_non_empty(simulation_id, "simulation id"),
        "source_kind": source_kind.value,
    }
    digest = _stable_sha256(payload)[:PREDICTION_ID_DIGEST_LENGTH]
    return f"prediction-{digest}"


def _select_risk_profile(
    *,
    simulation: SimulationResult,
    risk_profile: RiskProfile | None,
    risk_comparison: RiskComparison | None,
) -> RiskProfile | None:
    if risk_profile is not None and risk_profile.simulation_id != simulation.simulation_id:
        raise ValueError("risk profile simulation_id must match prediction simulation_id")

    if risk_comparison is None:
        return risk_profile

    matching_profiles = tuple(
        profile
        for profile in risk_comparison.profiles
        if profile.simulation_id == simulation.simulation_id
    )
    if not matching_profiles:
        raise ValueError("risk comparison does not contain a profile for the simulation")

    selected_profile = matching_profiles[0]
    if risk_profile is not None and risk_profile.profile_id != selected_profile.profile_id:
        raise ValueError("risk profile must match the profile selected from risk comparison")

    return selected_profile


def _derive_disposition(
    *,
    confidence_assessment: ConfidenceAssessment,
    risk_profile: RiskProfile | None,
    policy_evaluation: PolicyEvaluation | None,
) -> PredictionDisposition:
    if policy_evaluation is not None:
        if policy_evaluation.decision is PolicyDecision.QUARANTINE:
            return PredictionDisposition.QUARANTINE
        if policy_evaluation.decision is PolicyDecision.DENY:
            return PredictionDisposition.DENY

    if risk_profile is not None:
        if risk_profile.recommendation is RiskRecommendation.QUARANTINE:
            return PredictionDisposition.QUARANTINE
        if risk_profile.recommendation is RiskRecommendation.DENY:
            return PredictionDisposition.DENY
        if risk_profile.recommendation is RiskRecommendation.CAUTION:
            return PredictionDisposition.CAUTION

    if policy_evaluation is not None and policy_evaluation.decision is PolicyDecision.CAUTION:
        return PredictionDisposition.CAUTION

    if confidence_assessment.tier in {ConfidenceTier.UNSUPPORTED, ConfidenceTier.LOW}:
        return PredictionDisposition.REVIEW

    return PredictionDisposition.ACCEPT


def _build_prediction_findings(
    *,
    confidence_assessment: ConfidenceAssessment,
    risk_profile: RiskProfile | None,
    policy_evaluation: PolicyEvaluation | None,
    reproducibility_manifest: ReproducibilityManifest | None,
) -> tuple[PredictionFinding, ...]:
    findings: list[PredictionFinding] = [
        PredictionFinding(
            code=f"confidence-{confidence_assessment.tier.value}",
            message=(
                "Prediction confidence tier is "
                f"{confidence_assessment.tier.value}."
            ),
            source=f"confidence:{confidence_assessment.assessment_id}",
        )
    ]

    if risk_profile is None:
        findings.append(
            PredictionFinding(
                code="risk-not-attached",
                message="No risk profile was attached to the prediction result.",
                source="risk",
            )
        )
    else:
        findings.append(
            PredictionFinding(
                code=f"risk-{risk_profile.recommendation.value}",
                message=(
                    "Risk profile recommendation is "
                    f"{risk_profile.recommendation.value}."
                ),
                source=f"risk:{risk_profile.profile_id}",
            )
        )

    if policy_evaluation is None:
        findings.append(
            PredictionFinding(
                code="policy-not-attached",
                message="No policy evaluation was attached to the prediction result.",
                source="policy",
            )
        )
    else:
        findings.append(
            PredictionFinding(
                code=f"policy-{policy_evaluation.decision.value}",
                message=f"Policy evaluation decision is {policy_evaluation.decision.value}.",
                source=f"policy:{policy_evaluation.policy_evaluation_id}",
            )
        )

    if reproducibility_manifest is None:
        findings.append(
            PredictionFinding(
                code="reproducibility-not-attached",
                message="No reproducibility manifest was attached to the prediction result.",
                source="reproducibility",
            )
        )
    else:
        findings.append(
            PredictionFinding(
                code="reproducibility-attached",
                message="Prediction result is linked to a reproducibility manifest.",
                source=f"reproducibility:{reproducibility_manifest.manifest_id}",
            )
        )

    return _normalize_findings(tuple(findings))


def _normalize_findings(findings: tuple[PredictionFinding, ...]) -> tuple[PredictionFinding, ...]:
    if not findings:
        raise ValueError("prediction result requires at least one finding")

    seen_codes: set[str] = set()
    normalized_findings: list[PredictionFinding] = []

    for finding in findings:
        if finding.code in seen_codes:
            raise ValueError(f"duplicate prediction finding code: {finding.code}")
        seen_codes.add(finding.code)
        normalized_findings.append(finding)

    return tuple(sorted(normalized_findings, key=lambda item: item.code))


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

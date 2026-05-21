"""Model-confidence tracking for IX-BlackFox-WorldTwin.

Model confidence must be earned from evidence, not assumed. This module tracks
how prediction sources gain or lose trust after reproducibility checks,
reality-delta reports, policy reviews, and human review. The result is a
bounded, deterministic profile that later adaptation gates can inspect.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.reality_delta import RealityDeltaReport, RealityDeltaVerdict

MODEL_CONFIDENCE_SCHEMA_VERSION = "model-confidence-v1"
MODEL_CONFIDENCE_ID_DIGEST_LENGTH = 16


class ModelTrustTier(StrEnum):
    """Conservative trust tier assigned to a model or prediction source."""

    SUSPENDED = "suspended"
    UNTRUSTED = "untrusted"
    WATCHLIST = "watchlist"
    CANDIDATE = "candidate"
    TRUSTED = "trusted"


class ModelConfidenceSourceKind(StrEnum):
    """Evidence source types that can affect model confidence."""

    REALITY_DELTA = "reality-delta"
    REPRODUCIBILITY_CHECK = "reproducibility-check"
    POLICY_EVALUATION = "policy-evaluation"
    HUMAN_REVIEW = "human-review"
    MANUAL_ADJUSTMENT = "manual-adjustment"


@dataclass(frozen=True, slots=True)
class ModelConfidenceObservation:
    """A bounded confidence update tied to one evidence artifact."""

    observation_id: str
    model_id: str
    source_kind: ModelConfidenceSourceKind
    source_id: str
    score_delta: float
    rationale: str
    created_at: datetime
    created_by: str
    tags: tuple[str, ...] = ()
    schema_version: str = MODEL_CONFIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a model-confidence observation."""

        object.__setattr__(
            self,
            "observation_id",
            _require_non_empty(self.observation_id, "observation id"),
        )
        object.__setattr__(self, "model_id", _require_non_empty(self.model_id, "model id"))
        object.__setattr__(self, "source_id", _require_non_empty(self.source_id, "source id"))
        object.__setattr__(
            self,
            "score_delta",
            _require_delta_float(self.score_delta, "score delta"),
        )
        object.__setattr__(self, "rationale", _require_non_empty(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "observation created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "tags",
            _normalize_unique_text_tuple(self.tags, "observation tag"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "model-confidence schema version"),
        )

    @property
    def is_positive(self) -> bool:
        """Return True when this observation increases confidence."""

        return self.score_delta > 0.0

    @property
    def is_negative(self) -> bool:
        """Return True when this observation decreases confidence."""

        return self.score_delta < 0.0

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "model_id": self.model_id,
            "observation_id": self.observation_id,
            "rationale": self.rationale,
            "schema_version": self.schema_version,
            "score_delta": self.score_delta,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "tags": list(self.tags),
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this observation."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ModelConfidenceProfile:
    """A deterministic trust profile for one model or prediction source."""

    profile_id: str
    model_id: str
    base_confidence: float
    confidence_score: float
    trust_tier: ModelTrustTier
    observations: tuple[ModelConfidenceObservation, ...]
    created_at: datetime
    created_by: str
    notes: tuple[str, ...] = ()
    schema_version: str = MODEL_CONFIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a model-confidence profile."""

        normalized_observations = _normalize_observations(self.observations)
        expected_score = calculate_model_confidence_score(
            base_confidence=self.base_confidence,
            observations=normalized_observations,
        )
        expected_tier = classify_model_trust_tier(expected_score)

        if not math.isclose(self.confidence_score, expected_score, abs_tol=1e-12):
            raise ValueError("model confidence_score must match base confidence and observations")
        if self.trust_tier is not expected_tier:
            raise ValueError("model trust_tier must match confidence_score")

        object.__setattr__(self, "profile_id", _require_non_empty(self.profile_id, "profile id"))
        object.__setattr__(self, "model_id", _require_non_empty(self.model_id, "model id"))
        object.__setattr__(
            self,
            "base_confidence",
            _require_unit_interval(self.base_confidence, "base confidence"),
        )
        object.__setattr__(
            self,
            "confidence_score",
            _require_unit_interval(self.confidence_score, "confidence score"),
        )
        object.__setattr__(self, "observations", normalized_observations)
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "profile created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(self, "notes", _normalize_unique_text_tuple(self.notes, "profile note"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "model-confidence schema version"),
        )

    @property
    def blocks_trust_increase(self) -> bool:
        """Return True when the profile should block trust-increase automation."""

        return self.trust_tier in {ModelTrustTier.SUSPENDED, ModelTrustTier.UNTRUSTED}

    @property
    def allows_adaptation_review(self) -> bool:
        """Return True when the model may move to adaptation review."""

        return self.trust_tier in {ModelTrustTier.CANDIDATE, ModelTrustTier.TRUSTED}

    def observation_ids(self) -> tuple[str, ...]:
        """Return observation ids in deterministic order."""

        return tuple(observation.observation_id for observation in self.observations)

    def net_observation_delta(self) -> float:
        """Return net score delta from all observations."""

        return sum(observation.score_delta for observation in self.observations)

    def negative_observations(self) -> tuple[ModelConfidenceObservation, ...]:
        """Return negative confidence observations."""

        return tuple(observation for observation in self.observations if observation.is_negative)

    def positive_observations(self) -> tuple[ModelConfidenceObservation, ...]:
        """Return positive confidence observations."""

        return tuple(observation for observation in self.observations if observation.is_positive)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and handoff."""

        return {
            "base_confidence": self.base_confidence,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "model_id": self.model_id,
            "notes": list(self.notes),
            "observations": [
                observation.canonical_payload() for observation in self.observations
            ],
            "profile_id": self.profile_id,
            "schema_version": self.schema_version,
            "trust_tier": self.trust_tier.value,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this profile."""

        return _stable_sha256(self.canonical_payload())


def create_model_confidence_observation(
    *,
    model_id: str,
    source_kind: ModelConfidenceSourceKind,
    source_id: str,
    score_delta: float,
    rationale: str,
    created_at: datetime,
    created_by: str,
    tags: tuple[str, ...] = (),
    observation_id: str | None = None,
) -> ModelConfidenceObservation:
    """Create a bounded model-confidence observation."""

    normalized_model_id = _require_non_empty(model_id, "model id")
    normalized_source_id = _require_non_empty(source_id, "source id")
    normalized_delta = _require_delta_float(score_delta, "score delta")
    normalized_rationale = _require_non_empty(rationale, "rationale")
    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "observation created_at",
    )
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_tags = _normalize_unique_text_tuple(tags, "observation tag")
    resolved_observation_id = observation_id or make_model_confidence_observation_id(
        model_id=normalized_model_id,
        source_kind=source_kind,
        source_id=normalized_source_id,
        score_delta=normalized_delta,
        rationale=normalized_rationale,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        tags=normalized_tags,
    )

    return ModelConfidenceObservation(
        observation_id=resolved_observation_id,
        model_id=normalized_model_id,
        source_kind=source_kind,
        source_id=normalized_source_id,
        score_delta=normalized_delta,
        rationale=normalized_rationale,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        tags=normalized_tags,
    )


def create_model_confidence_profile(
    *,
    model_id: str,
    base_confidence: float,
    observations: tuple[ModelConfidenceObservation, ...],
    created_at: datetime,
    created_by: str,
    notes: tuple[str, ...] = (),
    profile_id: str | None = None,
) -> ModelConfidenceProfile:
    """Create a model-confidence profile from evidence observations."""

    normalized_model_id = _require_non_empty(model_id, "model id")
    normalized_base = _require_unit_interval(base_confidence, "base confidence")
    normalized_observations = _normalize_observations(observations)
    normalized_created_at = _require_aware_utc_datetime(created_at, "profile created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_notes = _normalize_unique_text_tuple(notes, "profile note")
    confidence_score = calculate_model_confidence_score(
        base_confidence=normalized_base,
        observations=normalized_observations,
    )
    trust_tier = classify_model_trust_tier(confidence_score)
    resolved_profile_id = profile_id or make_model_confidence_profile_id(
        model_id=normalized_model_id,
        base_confidence=normalized_base,
        confidence_score=confidence_score,
        trust_tier=trust_tier,
        observations=normalized_observations,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        notes=normalized_notes,
    )

    return ModelConfidenceProfile(
        profile_id=resolved_profile_id,
        model_id=normalized_model_id,
        base_confidence=normalized_base,
        confidence_score=confidence_score,
        trust_tier=trust_tier,
        observations=normalized_observations,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        notes=normalized_notes,
    )


def create_reality_delta_confidence_observation(
    *,
    model_id: str,
    report: RealityDeltaReport,
    created_at: datetime,
    created_by: str,
) -> ModelConfidenceObservation:
    """Convert a reality-delta report into a model-confidence observation."""

    score_delta = _score_delta_for_reality_verdict(report.verdict)
    rationale = (
        f"Reality-delta verdict {report.verdict.value}; aggregate normalized error "
        f"{report.aggregate_normalized_error():.6f}."
    )

    return create_model_confidence_observation(
        model_id=model_id,
        source_kind=ModelConfidenceSourceKind.REALITY_DELTA,
        source_id=report.report_id,
        score_delta=score_delta,
        rationale=rationale,
        created_at=created_at,
        created_by=created_by,
        tags=("reality-delta", report.verdict.value),
    )


def update_model_confidence_from_reality_delta(
    *,
    profile: ModelConfidenceProfile,
    report: RealityDeltaReport,
    created_at: datetime,
    created_by: str,
) -> ModelConfidenceProfile:
    """Return an updated model-confidence profile after a reality-delta report."""

    observation = create_reality_delta_confidence_observation(
        model_id=profile.model_id,
        report=report,
        created_at=created_at,
        created_by=created_by,
    )

    return create_model_confidence_profile(
        model_id=profile.model_id,
        base_confidence=profile.base_confidence,
        observations=profile.observations + (observation,),
        created_at=created_at,
        created_by=created_by,
        notes=profile.notes,
    )


def calculate_model_confidence_score(
    *,
    base_confidence: float,
    observations: tuple[ModelConfidenceObservation, ...],
) -> float:
    """Calculate bounded confidence score from base confidence and observations."""

    base = _require_unit_interval(base_confidence, "base confidence")
    net_delta = sum(observation.score_delta for observation in _normalize_observations(observations))
    return min(1.0, max(0.0, base + net_delta))


def classify_model_trust_tier(confidence_score: float) -> ModelTrustTier:
    """Classify confidence score into a conservative trust tier."""

    score = _require_unit_interval(confidence_score, "confidence score")
    if score < 0.10:
        return ModelTrustTier.SUSPENDED
    if score < 0.35:
        return ModelTrustTier.UNTRUSTED
    if score < 0.60:
        return ModelTrustTier.WATCHLIST
    if score < 0.85:
        return ModelTrustTier.CANDIDATE
    return ModelTrustTier.TRUSTED


def make_model_confidence_observation_id(
    *,
    model_id: str,
    source_kind: ModelConfidenceSourceKind,
    source_id: str,
    score_delta: float,
    rationale: str,
    created_at: datetime,
    created_by: str,
    tags: tuple[str, ...] = (),
) -> str:
    """Create a deterministic model-confidence observation id."""

    payload = {
        "created_at": _require_aware_utc_datetime(
            created_at,
            "observation created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "model_id": _require_non_empty(model_id, "model id"),
        "rationale": _require_non_empty(rationale, "rationale"),
        "schema_version": MODEL_CONFIDENCE_SCHEMA_VERSION,
        "score_delta": _require_delta_float(score_delta, "score delta"),
        "source_id": _require_non_empty(source_id, "source id"),
        "source_kind": source_kind.value,
        "tags": list(_normalize_unique_text_tuple(tags, "observation tag")),
    }
    digest = _stable_sha256(payload)[:MODEL_CONFIDENCE_ID_DIGEST_LENGTH]
    return f"model-confidence-observation-{digest}"


def make_model_confidence_profile_id(
    *,
    model_id: str,
    base_confidence: float,
    confidence_score: float,
    trust_tier: ModelTrustTier,
    observations: tuple[ModelConfidenceObservation, ...],
    created_at: datetime,
    created_by: str,
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic model-confidence profile id."""

    payload = {
        "base_confidence": _require_unit_interval(base_confidence, "base confidence"),
        "confidence_score": _require_unit_interval(confidence_score, "confidence score"),
        "created_at": _require_aware_utc_datetime(
            created_at,
            "profile created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "model_id": _require_non_empty(model_id, "model id"),
        "notes": list(_normalize_unique_text_tuple(notes, "profile note")),
        "observations": [
            observation.canonical_payload()
            for observation in _normalize_observations(observations)
        ],
        "schema_version": MODEL_CONFIDENCE_SCHEMA_VERSION,
        "trust_tier": trust_tier.value,
    }
    digest = _stable_sha256(payload)[:MODEL_CONFIDENCE_ID_DIGEST_LENGTH]
    return f"model-confidence-profile-{digest}"


def _score_delta_for_reality_verdict(verdict: RealityDeltaVerdict) -> float:
    if verdict is RealityDeltaVerdict.MATCH:
        return 0.05
    if verdict is RealityDeltaVerdict.DRIFT:
        return -0.10
    if verdict is RealityDeltaVerdict.BREACH:
        return -0.25
    return -0.50


def _normalize_observations(
    observations: tuple[ModelConfidenceObservation, ...],
) -> tuple[ModelConfidenceObservation, ...]:
    seen_ids: set[str] = set()
    normalized: list[ModelConfidenceObservation] = []

    for observation in observations:
        if observation.observation_id in seen_ids:
            raise ValueError(f"duplicate model-confidence observation: {observation.observation_id}")
        seen_ids.add(observation.observation_id)
        normalized.append(observation)

    return tuple(
        sorted(
            normalized,
            key=lambda item: (
                item.created_at.isoformat(),
                item.observation_id,
            ),
        )
    )


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


def _require_delta_float(value: float, field_name: str) -> float:
    normalized_value = _require_finite_float(value, field_name)
    if normalized_value < -1.0 or normalized_value > 1.0:
        raise ValueError(f"{field_name} must be between -1.0 and 1.0")
    return normalized_value


def _require_unit_interval(value: float, field_name: str) -> float:
    normalized_value = _require_finite_float(value, field_name)
    if normalized_value < 0.0 or normalized_value > 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
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

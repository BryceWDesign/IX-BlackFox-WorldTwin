"""Uncertainty and confidence contracts for IX-BlackFox-WorldTwin.

WorldTwin predictions must carry explicit uncertainty. This module keeps
confidence values bounded, classifies trust tiers conservatively, and records
uncertainty bands that later scenario, receipt, reality-delta, and handoff
modules can inspect without treating predictions as authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

UNCERTAINTY_SCHEMA_VERSION = "uncertainty-v1"
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0
CONFIDENCE_DIGEST_LENGTH = 16


class ConfidenceTier(StrEnum):
    """Conservative confidence tiers for bounded WorldTwin evidence."""

    UNSUPPORTED = "unsupported"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    BOUNDED_HIGH = "bounded-high"


class UncertaintySource(StrEnum):
    """Sources that can explain why a prediction is uncertain."""

    MEASUREMENT_NOISE = "measurement-noise"
    MODEL_ERROR = "model-error"
    ASSUMPTION = "assumption"
    SCENARIO_BOUNDARY = "scenario-boundary"
    OUT_OF_DISTRIBUTION = "out-of-distribution"
    HUMAN_JUDGMENT = "human-judgment"


@dataclass(frozen=True, slots=True)
class UncertaintyBand:
    """A bounded scalar interval attached to a predicted or observed dimension."""

    name: str
    lower_bound: float
    upper_bound: float
    unit: str
    confidence: float
    source: UncertaintySource
    rationale: str
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and normalize an uncertainty band."""

        name = _require_non_empty(self.name, "uncertainty band name")
        unit = _require_non_empty(self.unit, "uncertainty band unit")
        lower_bound = _require_finite_float(self.lower_bound, "uncertainty lower bound")
        upper_bound = _require_finite_float(self.upper_bound, "uncertainty upper bound")
        confidence = validate_confidence(self.confidence, "uncertainty band confidence")
        rationale = _require_non_empty(self.rationale, "uncertainty band rationale")
        tags = _normalize_text_tuple(self.tags, "uncertainty tag")

        if lower_bound > upper_bound:
            raise ValueError("uncertainty lower bound must be less than or equal to upper bound")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "lower_bound", lower_bound)
        object.__setattr__(self, "upper_bound", upper_bound)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "tags", tags)

    def width(self) -> float:
        """Return the scalar width of the uncertainty interval."""

        return self.upper_bound - self.lower_bound

    def midpoint(self) -> float:
        """Return the midpoint of the uncertainty interval."""

        return (self.lower_bound + self.upper_bound) / 2.0

    def contains(self, value: float) -> bool:
        """Return True when a finite value falls inside the interval."""

        checked_value = _require_finite_float(value, "uncertainty contains value")
        return self.lower_bound <= checked_value <= self.upper_bound

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "confidence": self.confidence,
            "lower_bound": self.lower_bound,
            "name": self.name,
            "rationale": self.rationale,
            "source": self.source.value,
            "tags": list(self.tags),
            "unit": self.unit,
            "upper_bound": self.upper_bound,
        }


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    """A confidence assessment for a scenario, model, prediction, or handoff target."""

    assessment_id: str
    target_id: str
    confidence: float
    tier: ConfidenceTier
    rationale: str
    created_at: datetime
    assessor: str
    evidence_ids: tuple[str, ...] = ()
    uncertainty_bands: tuple[UncertaintyBand, ...] = ()
    schema_version: str = UNCERTAINTY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a confidence assessment."""

        confidence = validate_confidence(self.confidence, "confidence assessment value")
        expected_tier = classify_confidence(confidence)
        if self.tier is not expected_tier:
            raise ValueError(
                "confidence assessment tier must match the normalized confidence value"
            )

        object.__setattr__(
            self,
            "assessment_id",
            _require_non_empty(self.assessment_id, "confidence assessment id"),
        )
        object.__setattr__(self, "target_id", _require_non_empty(self.target_id, "target id"))
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "rationale", _require_non_empty(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "confidence assessment created_at"),
        )
        object.__setattr__(self, "assessor", _require_non_empty(self.assessor, "assessor"))
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_unique_text_tuple(self.evidence_ids, "evidence id"),
        )
        object.__setattr__(
            self,
            "uncertainty_bands",
            _normalize_uncertainty_bands(self.uncertainty_bands),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "uncertainty schema version"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipt generation."""

        return {
            "assessment_id": self.assessment_id,
            "assessor": self.assessor,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "evidence_ids": list(self.evidence_ids),
            "rationale": self.rationale,
            "schema_version": self.schema_version,
            "target_id": self.target_id,
            "tier": self.tier.value,
            "uncertainty_bands": [
                band.canonical_payload() for band in self.uncertainty_bands
            ],
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this assessment."""

        return _stable_sha256(self.canonical_payload())


def create_confidence_assessment(
    *,
    target_id: str,
    confidence: float,
    rationale: str,
    created_at: datetime,
    assessor: str,
    evidence_ids: tuple[str, ...] = (),
    uncertainty_bands: tuple[UncertaintyBand, ...] = (),
    assessment_id: str | None = None,
) -> ConfidenceAssessment:
    """Create a validated confidence assessment with a deterministic id by default."""

    normalized_confidence = validate_confidence(confidence, "confidence assessment value")
    tier = classify_confidence(normalized_confidence)
    normalized_target_id = _require_non_empty(target_id, "target id")
    normalized_rationale = _require_non_empty(rationale, "rationale")
    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "confidence assessment created_at",
    )
    normalized_assessor = _require_non_empty(assessor, "assessor")
    normalized_evidence_ids = _normalize_unique_text_tuple(evidence_ids, "evidence id")
    normalized_bands = _normalize_uncertainty_bands(uncertainty_bands)
    resolved_assessment_id = assessment_id or make_confidence_assessment_id(
        target_id=normalized_target_id,
        confidence=normalized_confidence,
        rationale=normalized_rationale,
        created_at=normalized_created_at,
        assessor=normalized_assessor,
        evidence_ids=normalized_evidence_ids,
        uncertainty_bands=normalized_bands,
    )

    return ConfidenceAssessment(
        assessment_id=resolved_assessment_id,
        target_id=normalized_target_id,
        confidence=normalized_confidence,
        tier=tier,
        rationale=normalized_rationale,
        created_at=normalized_created_at,
        assessor=normalized_assessor,
        evidence_ids=normalized_evidence_ids,
        uncertainty_bands=normalized_bands,
    )


def make_confidence_assessment_id(
    *,
    target_id: str,
    confidence: float,
    rationale: str,
    created_at: datetime,
    assessor: str,
    evidence_ids: tuple[str, ...] = (),
    uncertainty_bands: tuple[UncertaintyBand, ...] = (),
) -> str:
    """Create a deterministic confidence assessment id."""

    payload = {
        "assessor": _require_non_empty(assessor, "assessor"),
        "confidence": validate_confidence(confidence, "confidence assessment value"),
        "created_at": _require_aware_utc_datetime(
            created_at,
            "confidence assessment created_at",
        ).isoformat(),
        "evidence_ids": list(_normalize_unique_text_tuple(evidence_ids, "evidence id")),
        "rationale": _require_non_empty(rationale, "rationale"),
        "schema_version": UNCERTAINTY_SCHEMA_VERSION,
        "target_id": _require_non_empty(target_id, "target id"),
        "uncertainty_bands": [
            band.canonical_payload()
            for band in _normalize_uncertainty_bands(uncertainty_bands)
        ],
    }
    digest = _stable_sha256(payload)[:CONFIDENCE_DIGEST_LENGTH]
    return f"confidence-assessment-{digest}"


def validate_confidence(value: float, field_name: str = "confidence") -> float:
    """Validate a confidence value on the closed interval [0.0, 1.0]."""

    confidence = _require_finite_float(value, field_name)
    if confidence < CONFIDENCE_MIN or confidence > CONFIDENCE_MAX:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return confidence


def classify_confidence(confidence: float) -> ConfidenceTier:
    """Classify confidence conservatively into a bounded trust tier."""

    value = validate_confidence(confidence)
    if value < 0.25:
        return ConfidenceTier.UNSUPPORTED
    if value < 0.50:
        return ConfidenceTier.LOW
    if value < 0.75:
        return ConfidenceTier.MODERATE
    if value < 0.90:
        return ConfidenceTier.HIGH
    return ConfidenceTier.BOUNDED_HIGH


def combine_confidence_conservatively(values: tuple[float, ...]) -> float:
    """Return the lowest confidence value from a non-empty group of values."""

    if not values:
        raise ValueError("at least one confidence value is required")
    return min(validate_confidence(value) for value in values)


def _normalize_uncertainty_bands(
    bands: tuple[UncertaintyBand, ...],
) -> tuple[UncertaintyBand, ...]:
    seen_names: set[str] = set()
    normalized_bands: list[UncertaintyBand] = []

    for band in bands:
        if band.name in seen_names:
            raise ValueError(f"duplicate uncertainty band: {band.name}")
        seen_names.add(band.name)
        normalized_bands.append(band)

    return tuple(sorted(normalized_bands, key=lambda band: band.name))


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


def _require_non_empty(value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")
    return normalized_value


def _require_finite_float(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return float(value)


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()

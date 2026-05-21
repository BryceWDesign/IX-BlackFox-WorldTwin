"""Reality-delta scoring for IX-BlackFox-WorldTwin.

Reality-delta scoring compares predicted final state against later observed
reality. This is the accountability loop: predictions do not get to remain
trusted just because they were receipted. Their error is measured, classified,
and preserved as reviewable evidence.
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

from ix_blackfox_worldtwin.prediction import PredictionResult
from ix_blackfox_worldtwin.state import WorldState, WorldStateKind

REALITY_DELTA_SCHEMA_VERSION = "reality-delta-v1"
REALITY_DELTA_ID_DIGEST_LENGTH = 16


class RealityDeltaSeverity(StrEnum):
    """Severity tier for prediction-vs-reality error."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RealityDeltaVerdict(StrEnum):
    """Aggregate verdict for a reality-delta report."""

    MATCH = "match"
    DRIFT = "drift"
    BREACH = "breach"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class DimensionDelta:
    """Prediction-vs-reality delta for one scalar dimension."""

    name: str
    predicted_value: float
    observed_value: float
    absolute_error: float
    tolerance: float
    normalized_error: float
    unit: str
    severity: RealityDeltaSeverity
    rationale: str
    schema_version: str = REALITY_DELTA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a dimension delta."""

        object.__setattr__(self, "name", _require_non_empty(self.name, "delta dimension name"))
        object.__setattr__(
            self,
            "predicted_value",
            _require_finite_float(self.predicted_value, "predicted value"),
        )
        object.__setattr__(
            self,
            "observed_value",
            _require_finite_float(self.observed_value, "observed value"),
        )
        object.__setattr__(
            self,
            "absolute_error",
            _require_non_negative_float(self.absolute_error, "absolute error"),
        )
        object.__setattr__(
            self,
            "tolerance",
            _require_positive_float(self.tolerance, "delta tolerance"),
        )
        object.__setattr__(
            self,
            "normalized_error",
            _require_non_negative_float(self.normalized_error, "normalized error"),
        )
        object.__setattr__(self, "unit", _require_non_empty(self.unit, "delta unit"))
        object.__setattr__(self, "rationale", _require_non_empty(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "reality-delta schema version"),
        )

    @property
    def passed(self) -> bool:
        """Return True when this dimension remains within tolerance."""

        return self.severity is RealityDeltaSeverity.INFO

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "absolute_error": self.absolute_error,
            "name": self.name,
            "normalized_error": self.normalized_error,
            "observed_value": self.observed_value,
            "predicted_value": self.predicted_value,
            "rationale": self.rationale,
            "schema_version": self.schema_version,
            "severity": self.severity.value,
            "tolerance": self.tolerance,
            "unit": self.unit,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this dimension delta."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class RealityDeltaReport:
    """A prediction accountability report comparing predicted state to reality."""

    report_id: str
    prediction_id: str
    scenario_id: str
    predicted_state_id: str
    observed_state_id: str
    created_at: datetime
    created_by: str
    verdict: RealityDeltaVerdict
    deltas: tuple[DimensionDelta, ...]
    missing_predicted_dimensions: tuple[str, ...] = ()
    missing_observed_dimensions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    schema_version: str = REALITY_DELTA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a reality-delta report."""

        object.__setattr__(self, "report_id", _require_non_empty(self.report_id, "report id"))
        object.__setattr__(
            self,
            "prediction_id",
            _require_non_empty(self.prediction_id, "prediction id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "predicted_state_id",
            _require_non_empty(self.predicted_state_id, "predicted state id"),
        )
        object.__setattr__(
            self,
            "observed_state_id",
            _require_non_empty(self.observed_state_id, "observed state id"),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "reality-delta created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(self, "deltas", _normalize_dimension_deltas(self.deltas))
        object.__setattr__(
            self,
            "missing_predicted_dimensions",
            _normalize_unique_text_tuple(
                self.missing_predicted_dimensions,
                "missing predicted dimension",
            ),
        )
        object.__setattr__(
            self,
            "missing_observed_dimensions",
            _normalize_unique_text_tuple(
                self.missing_observed_dimensions,
                "missing observed dimension",
            ),
        )
        object.__setattr__(self, "notes", _normalize_unique_text_tuple(self.notes, "delta note"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "reality-delta schema version"),
        )

        expected_verdict = classify_reality_delta_verdict(
            deltas=self.deltas,
            missing_predicted_dimensions=self.missing_predicted_dimensions,
            missing_observed_dimensions=self.missing_observed_dimensions,
        )
        if self.verdict is not expected_verdict:
            raise ValueError("reality-delta verdict must match delta and missing-dimension state")

    @property
    def passed(self) -> bool:
        """Return True when the report finds prediction and reality matched."""

        return self.verdict is RealityDeltaVerdict.MATCH

    @property
    def blocks_trust_increase(self) -> bool:
        """Return True when the report should block confidence increase."""

        return self.verdict in {
            RealityDeltaVerdict.BREACH,
            RealityDeltaVerdict.QUARANTINE,
        }

    def aggregate_normalized_error(self) -> float:
        """Return mean normalized error across compared dimensions."""

        if not self.deltas:
            return 0.0
        return sum(delta.normalized_error for delta in self.deltas) / len(self.deltas)

    def failed_deltas(self) -> tuple[DimensionDelta, ...]:
        """Return deltas outside clean match tolerance."""

        return tuple(delta for delta in self.deltas if not delta.passed)

    def highest_delta_severity(self) -> RealityDeltaSeverity:
        """Return highest severity across deltas and missing-dimension state."""

        if self.missing_predicted_dimensions or self.missing_observed_dimensions:
            return RealityDeltaSeverity.CRITICAL
        if not self.deltas:
            return RealityDeltaSeverity.CRITICAL
        return max((delta.severity for delta in self.deltas), key=_severity_rank)

    def delta_table(self) -> dict[str, float]:
        """Return dimension names mapped to normalized error."""

        return {delta.name: delta.normalized_error for delta in self.deltas}

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "deltas": [delta.canonical_payload() for delta in self.deltas],
            "missing_observed_dimensions": list(self.missing_observed_dimensions),
            "missing_predicted_dimensions": list(self.missing_predicted_dimensions),
            "notes": list(self.notes),
            "observed_state_id": self.observed_state_id,
            "predicted_state_id": self.predicted_state_id,
            "prediction_id": self.prediction_id,
            "report_id": self.report_id,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "verdict": self.verdict.value,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this report."""

        return _stable_sha256(self.canonical_payload())


def create_dimension_delta(
    *,
    name: str,
    predicted_value: float,
    observed_value: float,
    tolerance: float,
    unit: str,
) -> DimensionDelta:
    """Create a prediction-vs-reality delta for one scalar dimension."""

    normalized_name = _require_non_empty(name, "delta dimension name")
    normalized_predicted = _require_finite_float(predicted_value, "predicted value")
    normalized_observed = _require_finite_float(observed_value, "observed value")
    normalized_tolerance = _require_positive_float(tolerance, "delta tolerance")
    normalized_unit = _require_non_empty(unit, "delta unit")
    absolute_error = abs(normalized_observed - normalized_predicted)
    normalized_error = absolute_error / normalized_tolerance
    severity = classify_reality_delta_severity(normalized_error)
    rationale = (
        f"Observed value differed from predicted value by {absolute_error} "
        f"{normalized_unit} against tolerance {normalized_tolerance}."
    )

    return DimensionDelta(
        name=normalized_name,
        predicted_value=normalized_predicted,
        observed_value=normalized_observed,
        absolute_error=absolute_error,
        tolerance=normalized_tolerance,
        normalized_error=normalized_error,
        unit=normalized_unit,
        severity=severity,
        rationale=rationale,
    )


def create_reality_delta_report(
    *,
    prediction: PredictionResult,
    observed_state: WorldState,
    tolerances: Mapping[str, float],
    created_at: datetime,
    created_by: str,
    notes: tuple[str, ...] = (),
    report_id: str | None = None,
) -> RealityDeltaReport:
    """Compare a prediction result against later observed reality."""

    if observed_state.kind is not WorldStateKind.OBSERVED:
        raise ValueError("reality-delta observed_state must be observed reality")

    normalized_tolerances = _normalize_tolerances(tolerances)
    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "reality-delta created_at",
    )
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_notes = _normalize_unique_text_tuple(notes, "delta note")
    predicted_dimensions = {
        dimension.name: dimension for dimension in prediction.final_state.dimensions
    }
    observed_dimensions = {
        dimension.name: dimension for dimension in observed_state.dimensions
    }
    compared_names = tuple(sorted(set(predicted_dimensions) & set(observed_dimensions)))
    missing_predicted = tuple(sorted(set(observed_dimensions) - set(predicted_dimensions)))
    missing_observed = tuple(sorted(set(predicted_dimensions) - set(observed_dimensions)))

    deltas: list[DimensionDelta] = []
    for name in compared_names:
        if name not in normalized_tolerances:
            raise ValueError(f"missing reality-delta tolerance for dimension: {name}")

        predicted_dimension = predicted_dimensions[name]
        observed_dimension = observed_dimensions[name]
        deltas.append(
            create_dimension_delta(
                name=name,
                predicted_value=predicted_dimension.value,
                observed_value=observed_dimension.value,
                tolerance=normalized_tolerances[name],
                unit=observed_dimension.unit,
            )
        )

    normalized_deltas = _normalize_dimension_deltas(tuple(deltas))
    verdict = classify_reality_delta_verdict(
        deltas=normalized_deltas,
        missing_predicted_dimensions=missing_predicted,
        missing_observed_dimensions=missing_observed,
    )
    resolved_report_id = report_id or make_reality_delta_report_id(
        prediction_id=prediction.prediction_id,
        scenario_id=prediction.scenario_id,
        predicted_state_id=prediction.final_state.state_id,
        observed_state_id=observed_state.state_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        verdict=verdict,
        deltas=normalized_deltas,
        missing_predicted_dimensions=missing_predicted,
        missing_observed_dimensions=missing_observed,
        notes=normalized_notes,
    )

    return RealityDeltaReport(
        report_id=resolved_report_id,
        prediction_id=prediction.prediction_id,
        scenario_id=prediction.scenario_id,
        predicted_state_id=prediction.final_state.state_id,
        observed_state_id=observed_state.state_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        verdict=verdict,
        deltas=normalized_deltas,
        missing_predicted_dimensions=missing_predicted,
        missing_observed_dimensions=missing_observed,
        notes=normalized_notes,
    )


def classify_reality_delta_severity(normalized_error: float) -> RealityDeltaSeverity:
    """Classify one normalized error value into severity."""

    normalized_value = _require_non_negative_float(normalized_error, "normalized error")
    if normalized_value >= 5.0:
        return RealityDeltaSeverity.CRITICAL
    if normalized_value >= 2.0:
        return RealityDeltaSeverity.ERROR
    if normalized_value > 1.0:
        return RealityDeltaSeverity.WARNING
    return RealityDeltaSeverity.INFO


def classify_reality_delta_verdict(
    *,
    deltas: tuple[DimensionDelta, ...],
    missing_predicted_dimensions: tuple[str, ...] = (),
    missing_observed_dimensions: tuple[str, ...] = (),
) -> RealityDeltaVerdict:
    """Classify aggregate prediction-vs-reality outcome."""

    if missing_predicted_dimensions or missing_observed_dimensions:
        return RealityDeltaVerdict.QUARANTINE
    if not deltas:
        return RealityDeltaVerdict.QUARANTINE

    highest_severity = max((delta.severity for delta in deltas), key=_severity_rank)
    if highest_severity is RealityDeltaSeverity.CRITICAL:
        return RealityDeltaVerdict.QUARANTINE
    if highest_severity is RealityDeltaSeverity.ERROR:
        return RealityDeltaVerdict.BREACH
    if highest_severity is RealityDeltaSeverity.WARNING:
        return RealityDeltaVerdict.DRIFT
    return RealityDeltaVerdict.MATCH


def make_reality_delta_report_id(
    *,
    prediction_id: str,
    scenario_id: str,
    predicted_state_id: str,
    observed_state_id: str,
    created_at: datetime,
    created_by: str,
    verdict: RealityDeltaVerdict,
    deltas: tuple[DimensionDelta, ...],
    missing_predicted_dimensions: tuple[str, ...] = (),
    missing_observed_dimensions: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic reality-delta report id."""

    payload = {
        "created_at": _require_aware_utc_datetime(
            created_at,
            "reality-delta created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "deltas": [
            delta.canonical_payload() for delta in _normalize_dimension_deltas(deltas)
        ],
        "missing_observed_dimensions": list(
            _normalize_unique_text_tuple(
                missing_observed_dimensions,
                "missing observed dimension",
            )
        ),
        "missing_predicted_dimensions": list(
            _normalize_unique_text_tuple(
                missing_predicted_dimensions,
                "missing predicted dimension",
            )
        ),
        "notes": list(_normalize_unique_text_tuple(notes, "delta note")),
        "observed_state_id": _require_non_empty(observed_state_id, "observed state id"),
        "predicted_state_id": _require_non_empty(predicted_state_id, "predicted state id"),
        "prediction_id": _require_non_empty(prediction_id, "prediction id"),
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": REALITY_DELTA_SCHEMA_VERSION,
        "verdict": verdict.value,
    }
    digest = _stable_sha256(payload)[:REALITY_DELTA_ID_DIGEST_LENGTH]
    return f"reality-delta-{digest}"


def _normalize_tolerances(tolerances: Mapping[str, float]) -> dict[str, float]:
    if not tolerances:
        raise ValueError("reality-delta scoring requires at least one tolerance")

    normalized: dict[str, float] = {}
    for name, tolerance in tolerances.items():
        normalized_name = _require_non_empty(name, "tolerance dimension name")
        if normalized_name in normalized:
            raise ValueError(f"duplicate tolerance dimension: {normalized_name}")
        normalized[normalized_name] = _require_positive_float(tolerance, "delta tolerance")

    return dict(sorted(normalized.items()))


def _normalize_dimension_deltas(deltas: tuple[DimensionDelta, ...]) -> tuple[DimensionDelta, ...]:
    seen_names: set[str] = set()
    normalized_deltas: list[DimensionDelta] = []

    for delta in deltas:
        if delta.name in seen_names:
            raise ValueError(f"duplicate reality-delta dimension: {delta.name}")
        seen_names.add(delta.name)
        normalized_deltas.append(delta)

    return tuple(sorted(normalized_deltas, key=lambda item: item.name))


def _severity_rank(severity: RealityDeltaSeverity) -> int:
    ranks = {
        RealityDeltaSeverity.INFO: 0,
        RealityDeltaSeverity.WARNING: 1,
        RealityDeltaSeverity.ERROR: 2,
        RealityDeltaSeverity.CRITICAL: 3,
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


def _require_positive_float(value: float, field_name: str) -> float:
    normalized_value = _require_finite_float(value, field_name)
    if normalized_value <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized_value


def _require_non_negative_float(value: float, field_name: str) -> float:
    normalized_value = _require_finite_float(value, field_name)
    if normalized_value < 0.0:
        raise ValueError(f"{field_name} must be greater than or equal to zero")
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

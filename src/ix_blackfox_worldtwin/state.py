"""Typed world-state contracts for IX-BlackFox-WorldTwin.

WorldTwin treats every observed, simulated, or predicted state as a bounded
packet. State packets are not authority; they are reviewable evidence inputs
for scenario testing, prediction receipts, reality-delta scoring, and later
human-authorized execution review.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

STATE_SCHEMA_VERSION = "world-state-v1"
STATE_ID_DIGEST_LENGTH = 16


class WorldStateKind(StrEnum):
    """Supported categories of world-state packet."""

    OBSERVED = "observed"
    SIMULATED = "simulated"
    PREDICTED = "predicted"


@dataclass(frozen=True, slots=True)
class StateDimension:
    """A single measured, simulated, or predicted scalar dimension."""

    name: str
    value: float
    unit: str
    description: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate and normalize a state dimension."""

        name = _require_non_empty(self.name, "dimension name")
        unit = _require_non_empty(self.unit, "dimension unit")
        description = self.description.strip()
        value = _require_finite_float(self.value, "dimension value")
        tags = _normalize_text_tuple(self.tags, "dimension tag")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "tags", tags)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipt generation."""

        return {
            "description": self.description,
            "name": self.name,
            "tags": list(self.tags),
            "unit": self.unit,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class WorldState:
    """A bounded state packet used by WorldTwin scenario and prediction logic."""

    state_id: str
    kind: WorldStateKind
    dimensions: tuple[StateDimension, ...]
    valid_at: datetime
    created_at: datetime
    source: str
    lineage: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    schema_version: str = STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a world-state packet."""

        state_id = _require_non_empty(self.state_id, "state id")
        source = _require_non_empty(self.source, "state source")
        schema_version = _require_non_empty(self.schema_version, "state schema version")
        dimensions = _normalize_dimensions(self.dimensions)
        valid_at = _require_aware_utc_datetime(self.valid_at, "state valid_at")
        created_at = _require_aware_utc_datetime(self.created_at, "state created_at")
        lineage = _normalize_text_tuple(self.lineage, "state lineage id")
        notes = _normalize_text_tuple(self.notes, "state note")

        object.__setattr__(self, "state_id", state_id)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "dimensions", dimensions)
        object.__setattr__(self, "valid_at", valid_at)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "lineage", lineage)
        object.__setattr__(self, "notes", notes)

    def get_dimension(self, name: str) -> StateDimension:
        """Return a dimension by name or raise KeyError when missing."""

        normalized_name = _require_non_empty(name, "dimension lookup name")
        for dimension in self.dimensions:
            if dimension.name == normalized_name:
                return dimension
        raise KeyError(f"state dimension not found: {normalized_name}")

    def to_dimension_map(self) -> dict[str, float]:
        """Return dimension names mapped to scalar values."""

        return {dimension.name: dimension.value for dimension in self.dimensions}

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipt generation."""

        return _canonical_state_payload(
            state_id=self.state_id,
            kind=self.kind,
            dimensions=self.dimensions,
            valid_at=self.valid_at,
            created_at=self.created_at,
            source=self.source,
            lineage=self.lineage,
            notes=self.notes,
            schema_version=self.schema_version,
        )

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this state packet."""

        return _stable_sha256(self.canonical_payload())


def create_world_state(
    *,
    kind: WorldStateKind,
    dimensions: tuple[StateDimension, ...],
    valid_at: datetime,
    created_at: datetime,
    source: str,
    state_id: str | None = None,
    lineage: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> WorldState:
    """Create a validated world-state packet with a deterministic id by default."""

    normalized_dimensions = _normalize_dimensions(dimensions)
    normalized_valid_at = _require_aware_utc_datetime(valid_at, "state valid_at")
    normalized_created_at = _require_aware_utc_datetime(created_at, "state created_at")
    normalized_source = _require_non_empty(source, "state source")
    normalized_lineage = _normalize_text_tuple(lineage, "state lineage id")
    normalized_notes = _normalize_text_tuple(notes, "state note")
    resolved_state_id = state_id or make_state_id(
        kind=kind,
        dimensions=normalized_dimensions,
        valid_at=normalized_valid_at,
        created_at=normalized_created_at,
        source=normalized_source,
        lineage=normalized_lineage,
        notes=normalized_notes,
    )

    return WorldState(
        state_id=resolved_state_id,
        kind=kind,
        dimensions=normalized_dimensions,
        valid_at=normalized_valid_at,
        created_at=normalized_created_at,
        source=normalized_source,
        lineage=normalized_lineage,
        notes=normalized_notes,
    )


def create_observed_state(
    *,
    dimensions: tuple[StateDimension, ...],
    valid_at: datetime,
    created_at: datetime,
    source: str,
    state_id: str | None = None,
    lineage: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> WorldState:
    """Create a state packet for observed reality."""

    return create_world_state(
        kind=WorldStateKind.OBSERVED,
        dimensions=dimensions,
        valid_at=valid_at,
        created_at=created_at,
        source=source,
        state_id=state_id,
        lineage=lineage,
        notes=notes,
    )


def create_simulated_state(
    *,
    dimensions: tuple[StateDimension, ...],
    valid_at: datetime,
    created_at: datetime,
    source: str,
    state_id: str | None = None,
    lineage: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> WorldState:
    """Create a state packet for simulated state evolution."""

    return create_world_state(
        kind=WorldStateKind.SIMULATED,
        dimensions=dimensions,
        valid_at=valid_at,
        created_at=created_at,
        source=source,
        state_id=state_id,
        lineage=lineage,
        notes=notes,
    )


def create_predicted_state(
    *,
    dimensions: tuple[StateDimension, ...],
    valid_at: datetime,
    created_at: datetime,
    source: str,
    state_id: str | None = None,
    lineage: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> WorldState:
    """Create a state packet for predicted future state."""

    return create_world_state(
        kind=WorldStateKind.PREDICTED,
        dimensions=dimensions,
        valid_at=valid_at,
        created_at=created_at,
        source=source,
        state_id=state_id,
        lineage=lineage,
        notes=notes,
    )


def make_state_id(
    *,
    kind: WorldStateKind,
    dimensions: tuple[StateDimension, ...],
    valid_at: datetime,
    created_at: datetime,
    source: str,
    lineage: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic state id from the semantic state payload."""

    payload = _canonical_state_payload(
        state_id="",
        kind=kind,
        dimensions=_normalize_dimensions(dimensions),
        valid_at=_require_aware_utc_datetime(valid_at, "state valid_at"),
        created_at=_require_aware_utc_datetime(created_at, "state created_at"),
        source=_require_non_empty(source, "state source"),
        lineage=_normalize_text_tuple(lineage, "state lineage id"),
        notes=_normalize_text_tuple(notes, "state note"),
        schema_version=STATE_SCHEMA_VERSION,
    )
    digest = _stable_sha256(payload)[:STATE_ID_DIGEST_LENGTH]
    return f"{kind.value}-state-{digest}"


def _canonical_state_payload(
    *,
    state_id: str,
    kind: WorldStateKind,
    dimensions: tuple[StateDimension, ...],
    valid_at: datetime,
    created_at: datetime,
    source: str,
    lineage: tuple[str, ...],
    notes: tuple[str, ...],
    schema_version: str,
) -> dict[str, Any]:
    return {
        "created_at": created_at.isoformat(),
        "dimensions": [
            dimension.canonical_payload()
            for dimension in sorted(dimensions, key=lambda item: item.name)
        ],
        "kind": kind.value,
        "lineage": list(lineage),
        "notes": list(notes),
        "schema_version": schema_version,
        "source": source,
        "state_id": state_id,
        "valid_at": valid_at.isoformat(),
    }


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()


def _normalize_dimensions(dimensions: tuple[StateDimension, ...]) -> tuple[StateDimension, ...]:
    if not dimensions:
        raise ValueError("world state requires at least one dimension")

    names: set[str] = set()
    normalized_dimensions: list[StateDimension] = []
    for dimension in dimensions:
        if dimension.name in names:
            raise ValueError(f"duplicate state dimension: {dimension.name}")
        names.add(dimension.name)
        normalized_dimensions.append(dimension)

    return tuple(normalized_dimensions)


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

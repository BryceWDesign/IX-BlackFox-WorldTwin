"""Scenario manifest contracts for IX-BlackFox-WorldTwin.

A scenario manifest defines the bounded question WorldTwin is allowed to test.
It records the system under test, initial state, boundaries, variables,
measurable outputs, evidence references, and replay requirements without
claiming that the scenario is complete reality.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.state import WorldState

SCENARIO_SCHEMA_VERSION = "scenario-manifest-v1"
SCENARIO_ID_DIGEST_LENGTH = 16


class ScenarioBoundaryKind(StrEnum):
    """Supported scenario boundary categories."""

    TEMPORAL = "temporal"
    PHYSICAL = "physical"
    OPERATIONAL = "operational"
    POLICY = "policy"
    DATA = "data"
    HUMAN_REVIEW = "human-review"
    SAFETY = "safety"


class ScenarioVariableKind(StrEnum):
    """Supported variable roles inside a bounded scenario."""

    CONTROLLED = "controlled"
    OBSERVED = "observed"
    DISTURBANCE = "disturbance"
    DERIVED = "derived"


@dataclass(frozen=True, slots=True)
class ScenarioBoundary:
    """A named boundary that limits what a scenario is allowed to claim."""

    name: str
    kind: ScenarioBoundaryKind
    description: str
    is_hard_boundary: bool = True

    def __post_init__(self) -> None:
        """Validate and normalize a scenario boundary."""

        object.__setattr__(self, "name", _require_non_empty(self.name, "boundary name"))
        object.__setattr__(
            self,
            "description",
            _require_non_empty(self.description, "boundary description"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic boundary payload."""

        return {
            "description": self.description,
            "is_hard_boundary": self.is_hard_boundary,
            "kind": self.kind.value,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class ScenarioVariable:
    """A variable that can be observed, controlled, derived, or disturbed."""

    name: str
    kind: ScenarioVariableKind
    unit: str
    description: str
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        """Validate and normalize a scenario variable."""

        minimum = self.minimum
        maximum = self.maximum

        if minimum is not None:
            minimum = float(minimum)
        if maximum is not None:
            maximum = float(maximum)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("variable minimum must be less than or equal to maximum")

        object.__setattr__(self, "name", _require_non_empty(self.name, "variable name"))
        object.__setattr__(self, "unit", _require_non_empty(self.unit, "variable unit"))
        object.__setattr__(
            self,
            "description",
            _require_non_empty(self.description, "variable description"),
        )
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic variable payload."""

        return {
            "description": self.description,
            "kind": self.kind.value,
            "maximum": self.maximum,
            "minimum": self.minimum,
            "name": self.name,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class MeasurableOutput:
    """A required scenario output that can be checked after simulation."""

    name: str
    unit: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        """Validate and normalize a measurable output."""

        object.__setattr__(self, "name", _require_non_empty(self.name, "output name"))
        object.__setattr__(self, "unit", _require_non_empty(self.unit, "output unit"))
        object.__setattr__(
            self,
            "description",
            _require_non_empty(self.description, "output description"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic output payload."""

        return {
            "description": self.description,
            "name": self.name,
            "required": self.required,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ScenarioManifest:
    """A bounded and replayable scenario definition."""

    scenario_id: str
    title: str
    system_under_test: str
    purpose: str
    initial_state: WorldState
    boundaries: tuple[ScenarioBoundary, ...]
    variables: tuple[ScenarioVariable, ...]
    expected_outputs: tuple[MeasurableOutput, ...]
    created_at: datetime
    created_by: str
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    replay_required: bool = True
    schema_version: str = SCENARIO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a scenario manifest."""

        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(self, "title", _require_non_empty(self.title, "scenario title"))
        object.__setattr__(
            self,
            "system_under_test",
            _require_non_empty(self.system_under_test, "system under test"),
        )
        object.__setattr__(self, "purpose", _require_non_empty(self.purpose, "scenario purpose"))
        object.__setattr__(
            self,
            "boundaries",
            _normalize_named_items(self.boundaries, "scenario boundary"),
        )
        object.__setattr__(
            self,
            "variables",
            _normalize_named_items(self.variables, "scenario variable"),
        )
        object.__setattr__(
            self,
            "expected_outputs",
            _normalize_named_items(self.expected_outputs, "measurable output"),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "scenario created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_unique_text_tuple(self.evidence_ids, "evidence id"),
        )
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "scenario tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "scenario schema version"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing, receipts, and replay."""

        return _canonical_scenario_payload(
            scenario_id=self.scenario_id,
            title=self.title,
            system_under_test=self.system_under_test,
            purpose=self.purpose,
            initial_state=self.initial_state,
            boundaries=self.boundaries,
            variables=self.variables,
            expected_outputs=self.expected_outputs,
            created_at=self.created_at,
            created_by=self.created_by,
            evidence_ids=self.evidence_ids,
            tags=self.tags,
            replay_required=self.replay_required,
            schema_version=self.schema_version,
        )

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this scenario."""

        return _stable_sha256(self.canonical_payload())

    def required_output_names(self) -> tuple[str, ...]:
        """Return names of outputs that must appear in simulation results."""

        return tuple(output.name for output in self.expected_outputs if output.required)


def create_scenario_manifest(
    *,
    title: str,
    system_under_test: str,
    purpose: str,
    initial_state: WorldState,
    boundaries: tuple[ScenarioBoundary, ...],
    variables: tuple[ScenarioVariable, ...],
    expected_outputs: tuple[MeasurableOutput, ...],
    created_at: datetime,
    created_by: str,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    replay_required: bool = True,
    scenario_id: str | None = None,
) -> ScenarioManifest:
    """Create a validated scenario manifest with a deterministic id by default."""

    normalized_title = _require_non_empty(title, "scenario title")
    normalized_system = _require_non_empty(system_under_test, "system under test")
    normalized_purpose = _require_non_empty(purpose, "scenario purpose")
    normalized_boundaries = _normalize_named_items(boundaries, "scenario boundary")
    normalized_variables = _normalize_named_items(variables, "scenario variable")
    normalized_outputs = _normalize_named_items(expected_outputs, "measurable output")
    normalized_created_at = _require_aware_utc_datetime(created_at, "scenario created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_evidence_ids = _normalize_unique_text_tuple(evidence_ids, "evidence id")
    normalized_tags = _normalize_unique_text_tuple(tags, "scenario tag")
    resolved_scenario_id = scenario_id or make_scenario_id(
        title=normalized_title,
        system_under_test=normalized_system,
        purpose=normalized_purpose,
        initial_state=initial_state,
        boundaries=normalized_boundaries,
        variables=normalized_variables,
        expected_outputs=normalized_outputs,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
        replay_required=replay_required,
    )

    return ScenarioManifest(
        scenario_id=resolved_scenario_id,
        title=normalized_title,
        system_under_test=normalized_system,
        purpose=normalized_purpose,
        initial_state=initial_state,
        boundaries=normalized_boundaries,
        variables=normalized_variables,
        expected_outputs=normalized_outputs,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
        replay_required=replay_required,
    )


def make_scenario_id(
    *,
    title: str,
    system_under_test: str,
    purpose: str,
    initial_state: WorldState,
    boundaries: tuple[ScenarioBoundary, ...],
    variables: tuple[ScenarioVariable, ...],
    expected_outputs: tuple[MeasurableOutput, ...],
    created_at: datetime,
    created_by: str,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    replay_required: bool = True,
) -> str:
    """Create a deterministic scenario id from the scenario manifest payload."""

    payload = _canonical_scenario_payload(
        scenario_id="",
        title=_require_non_empty(title, "scenario title"),
        system_under_test=_require_non_empty(system_under_test, "system under test"),
        purpose=_require_non_empty(purpose, "scenario purpose"),
        initial_state=initial_state,
        boundaries=_normalize_named_items(boundaries, "scenario boundary"),
        variables=_normalize_named_items(variables, "scenario variable"),
        expected_outputs=_normalize_named_items(expected_outputs, "measurable output"),
        created_at=_require_aware_utc_datetime(created_at, "scenario created_at"),
        created_by=_require_non_empty(created_by, "created by"),
        evidence_ids=_normalize_unique_text_tuple(evidence_ids, "evidence id"),
        tags=_normalize_unique_text_tuple(tags, "scenario tag"),
        replay_required=replay_required,
        schema_version=SCENARIO_SCHEMA_VERSION,
    )
    digest = _stable_sha256(payload)[:SCENARIO_ID_DIGEST_LENGTH]
    return f"scenario-{digest}"


def _canonical_scenario_payload(
    *,
    scenario_id: str,
    title: str,
    system_under_test: str,
    purpose: str,
    initial_state: WorldState,
    boundaries: tuple[ScenarioBoundary, ...],
    variables: tuple[ScenarioVariable, ...],
    expected_outputs: tuple[MeasurableOutput, ...],
    created_at: datetime,
    created_by: str,
    evidence_ids: tuple[str, ...],
    tags: tuple[str, ...],
    replay_required: bool,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "boundaries": [boundary.canonical_payload() for boundary in boundaries],
        "created_at": created_at.isoformat(),
        "created_by": created_by,
        "evidence_ids": list(evidence_ids),
        "expected_outputs": [output.canonical_payload() for output in expected_outputs],
        "initial_state_fingerprint": initial_state.fingerprint(),
        "initial_state_id": initial_state.state_id,
        "purpose": purpose,
        "replay_required": replay_required,
        "scenario_id": scenario_id,
        "schema_version": schema_version,
        "system_under_test": system_under_test,
        "tags": list(tags),
        "title": title,
        "variables": [variable.canonical_payload() for variable in variables],
    }


def _normalize_named_items(
    items: tuple[ScenarioBoundary, ...]
    | tuple[ScenarioVariable, ...]
    | tuple[MeasurableOutput, ...],
    item_label: str,
) -> tuple[Any, ...]:
    if not items:
        raise ValueError(f"{item_label} list must not be empty")

    seen_names: set[str] = set()
    normalized_items: list[Any] = []

    for item in items:
        if item.name in seen_names:
            raise ValueError(f"duplicate {item_label}: {item.name}")
        seen_names.add(item.name)
        normalized_items.append(item)

    return tuple(sorted(normalized_items, key=lambda item: item.name))


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        normalized_values.append(_require_non_empty(value, field_name))

    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError(f"duplicate {field_name}")

    return tuple(sorted(normalized_values))


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

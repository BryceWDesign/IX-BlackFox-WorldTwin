"""Deterministic simulation kernel for IX-BlackFox-WorldTwin.

The Wave 1 simulation kernel is intentionally simple, dependency-light, and
replayable in normal CI. It does not claim physical completeness. It provides a
bounded state-transition mechanism that scenario, branching, prediction,
receipt, reality-delta, and handoff layers can inspect.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ix_blackfox_worldtwin.scenario import ScenarioManifest
from ix_blackfox_worldtwin.scenario_validation import ensure_scenario_manifest_replayable
from ix_blackfox_worldtwin.state import (
    StateDimension,
    WorldState,
    create_simulated_state,
)

SIMULATION_SCHEMA_VERSION = "deterministic-simulation-v1"
SIMULATION_ID_DIGEST_LENGTH = 16


@dataclass(frozen=True, slots=True)
class SimulationRule:
    """A deterministic per-step scalar transition rule."""

    rule_id: str
    target: str
    delta_per_step: float
    unit: str
    description: str
    initial_value: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    clamp_to_bounds: bool = False
    tags: tuple[str, ...] = ()
    schema_version: str = SIMULATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a simulation rule."""

        minimum = _normalize_optional_float(self.minimum, "simulation minimum")
        maximum = _normalize_optional_float(self.maximum, "simulation maximum")

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("simulation minimum must be less than or equal to maximum")

        object.__setattr__(self, "rule_id", _require_non_empty(self.rule_id, "simulation rule id"))
        object.__setattr__(self, "target", _require_non_empty(self.target, "simulation target"))
        object.__setattr__(
            self,
            "delta_per_step",
            _require_finite_float(self.delta_per_step, "simulation delta_per_step"),
        )
        object.__setattr__(self, "unit", _require_non_empty(self.unit, "simulation unit"))
        object.__setattr__(
            self,
            "description",
            _require_non_empty(self.description, "simulation description"),
        )
        object.__setattr__(
            self,
            "initial_value",
            _require_finite_float(self.initial_value, "simulation initial_value"),
        )
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "simulation tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "simulation schema version"),
        )

    def apply(self, current_value: float) -> float:
        """Apply this rule to a current scalar value."""

        next_value = _require_finite_float(current_value, "current simulation value")
        next_value += self.delta_per_step

        if self.clamp_to_bounds:
            if self.minimum is not None:
                next_value = max(next_value, self.minimum)
            if self.maximum is not None:
                next_value = min(next_value, self.maximum)

        return next_value

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "clamp_to_bounds": self.clamp_to_bounds,
            "delta_per_step": self.delta_per_step,
            "description": self.description,
            "initial_value": self.initial_value,
            "maximum": self.maximum,
            "minimum": self.minimum,
            "rule_id": self.rule_id,
            "schema_version": self.schema_version,
            "tags": list(self.tags),
            "target": self.target,
            "unit": self.unit,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this rule."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Configuration for one deterministic simulation run."""

    step_count: int
    step_seconds: int
    created_at: datetime
    kernel_name: str = "worldtwin-deterministic-kernel"
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    schema_version: str = SIMULATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize simulation configuration."""

        if self.step_count <= 0:
            raise ValueError("simulation step_count must be greater than zero")
        if self.step_seconds <= 0:
            raise ValueError("simulation step_seconds must be greater than zero")

        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "simulation created_at"),
        )
        object.__setattr__(
            self,
            "kernel_name",
            _require_non_empty(self.kernel_name, "simulation kernel name"),
        )
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_unique_text_tuple(self.evidence_ids, "evidence id"),
        )
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "simulation tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "simulation schema version"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "created_at": self.created_at.isoformat(),
            "evidence_ids": list(self.evidence_ids),
            "kernel_name": self.kernel_name,
            "schema_version": self.schema_version,
            "step_count": self.step_count,
            "step_seconds": self.step_seconds,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Result of a deterministic WorldTwin simulation run."""

    simulation_id: str
    scenario_id: str
    initial_state: WorldState
    states: tuple[WorldState, ...]
    rules: tuple[SimulationRule, ...]
    config: SimulationConfig
    missing_required_outputs: tuple[str, ...] = ()
    schema_version: str = SIMULATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a simulation result."""

        if not self.states:
            raise ValueError("simulation result requires at least one simulated state")
        if not self.rules:
            raise ValueError("simulation result requires at least one simulation rule")

        object.__setattr__(
            self,
            "simulation_id",
            _require_non_empty(self.simulation_id, "simulation id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(self, "states", tuple(self.states))
        object.__setattr__(self, "rules", _normalize_simulation_rules(self.rules))
        object.__setattr__(
            self,
            "missing_required_outputs",
            _normalize_unique_text_tuple(
                self.missing_required_outputs,
                "missing required output",
            ),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "simulation schema version"),
        )

    @property
    def final_state(self) -> WorldState:
        """Return the final simulated state."""

        return self.states[-1]

    def predicted_values(self) -> dict[str, float]:
        """Return final simulated dimension values."""

        return self.final_state.to_dimension_map()

    def step_count(self) -> int:
        """Return the number of simulated states produced."""

        return len(self.states)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "config": self.config.canonical_payload(),
            "initial_state_fingerprint": self.initial_state.fingerprint(),
            "initial_state_id": self.initial_state.state_id,
            "missing_required_outputs": list(self.missing_required_outputs),
            "rules": [rule.canonical_payload() for rule in self.rules],
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "simulation_id": self.simulation_id,
            "state_fingerprints": [state.fingerprint() for state in self.states],
            "state_ids": [state.state_id for state in self.states],
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this simulation result."""

        return _stable_sha256(self.canonical_payload())


def create_simulation_rule(
    *,
    target: str,
    delta_per_step: float,
    unit: str,
    description: str,
    initial_value: float = 0.0,
    minimum: float | None = None,
    maximum: float | None = None,
    clamp_to_bounds: bool = False,
    tags: tuple[str, ...] = (),
    rule_id: str | None = None,
) -> SimulationRule:
    """Create a validated simulation rule with a deterministic id by default."""

    normalized_target = _require_non_empty(target, "simulation target")
    normalized_delta = _require_finite_float(delta_per_step, "simulation delta_per_step")
    normalized_unit = _require_non_empty(unit, "simulation unit")
    normalized_description = _require_non_empty(description, "simulation description")
    normalized_initial = _require_finite_float(initial_value, "simulation initial_value")
    normalized_minimum = _normalize_optional_float(minimum, "simulation minimum")
    normalized_maximum = _normalize_optional_float(maximum, "simulation maximum")
    normalized_tags = _normalize_unique_text_tuple(tags, "simulation tag")
    resolved_rule_id = rule_id or make_simulation_rule_id(
        target=normalized_target,
        delta_per_step=normalized_delta,
        unit=normalized_unit,
        description=normalized_description,
        initial_value=normalized_initial,
        minimum=normalized_minimum,
        maximum=normalized_maximum,
        clamp_to_bounds=clamp_to_bounds,
        tags=normalized_tags,
    )

    return SimulationRule(
        rule_id=resolved_rule_id,
        target=normalized_target,
        delta_per_step=normalized_delta,
        unit=normalized_unit,
        description=normalized_description,
        initial_value=normalized_initial,
        minimum=normalized_minimum,
        maximum=normalized_maximum,
        clamp_to_bounds=clamp_to_bounds,
        tags=normalized_tags,
    )


def run_deterministic_simulation(
    *,
    scenario: ScenarioManifest,
    rules: tuple[SimulationRule, ...],
    config: SimulationConfig,
    simulation_id: str | None = None,
) -> SimulationResult:
    """Run a replayable deterministic simulation for a valid scenario."""

    ensure_scenario_manifest_replayable(scenario)
    normalized_rules = _normalize_simulation_rules(rules)
    values = dict(scenario.initial_state.to_dimension_map())
    units = {dimension.name: dimension.unit for dimension in scenario.initial_state.dimensions}
    descriptions = {
        dimension.name: dimension.description for dimension in scenario.initial_state.dimensions
    }

    for rule in normalized_rules:
        units[rule.target] = rule.unit
        descriptions[rule.target] = rule.description
        values.setdefault(rule.target, rule.initial_value)

    states: list[WorldState] = []
    lineage = (scenario.initial_state.state_id,)

    for step_index in range(1, config.step_count + 1):
        for rule in normalized_rules:
            values[rule.target] = rule.apply(values[rule.target])

        state = create_simulated_state(
            dimensions=_dimensions_from_values(values, units, descriptions),
            valid_at=scenario.initial_state.valid_at
            + timedelta(seconds=config.step_seconds * step_index),
            created_at=config.created_at,
            source=f"{config.kernel_name}:step-{step_index}",
            lineage=lineage,
            notes=(f"deterministic simulation step {step_index} of {config.step_count}",),
        )
        states.append(state)
        lineage = (state.state_id,)

    final_values = states[-1].to_dimension_map()
    missing_required_outputs = tuple(
        output_name
        for output_name in scenario.required_output_names()
        if output_name not in final_values
    )

    if missing_required_outputs:
        joined_outputs = ", ".join(missing_required_outputs)
        raise ValueError(f"simulation missing required outputs: {joined_outputs}")

    resolved_simulation_id = simulation_id or make_simulation_id(
        scenario_id=scenario.scenario_id,
        initial_state=scenario.initial_state,
        states=tuple(states),
        rules=normalized_rules,
        config=config,
        missing_required_outputs=missing_required_outputs,
    )

    return SimulationResult(
        simulation_id=resolved_simulation_id,
        scenario_id=scenario.scenario_id,
        initial_state=scenario.initial_state,
        states=tuple(states),
        rules=normalized_rules,
        config=config,
        missing_required_outputs=missing_required_outputs,
    )


def make_simulation_rule_id(
    *,
    target: str,
    delta_per_step: float,
    unit: str,
    description: str,
    initial_value: float = 0.0,
    minimum: float | None = None,
    maximum: float | None = None,
    clamp_to_bounds: bool = False,
    tags: tuple[str, ...] = (),
) -> str:
    """Create a deterministic simulation rule id."""

    payload = {
        "clamp_to_bounds": clamp_to_bounds,
        "delta_per_step": _require_finite_float(
            delta_per_step,
            "simulation delta_per_step",
        ),
        "description": _require_non_empty(description, "simulation description"),
        "initial_value": _require_finite_float(initial_value, "simulation initial_value"),
        "maximum": _normalize_optional_float(maximum, "simulation maximum"),
        "minimum": _normalize_optional_float(minimum, "simulation minimum"),
        "schema_version": SIMULATION_SCHEMA_VERSION,
        "tags": list(_normalize_unique_text_tuple(tags, "simulation tag")),
        "target": _require_non_empty(target, "simulation target"),
        "unit": _require_non_empty(unit, "simulation unit"),
    }
    digest = _stable_sha256(payload)[:SIMULATION_ID_DIGEST_LENGTH]
    return f"simulation-rule-{digest}"


def make_simulation_id(
    *,
    scenario_id: str,
    initial_state: WorldState,
    states: tuple[WorldState, ...],
    rules: tuple[SimulationRule, ...],
    config: SimulationConfig,
    missing_required_outputs: tuple[str, ...] = (),
) -> str:
    """Create a deterministic simulation result id."""

    if not states:
        raise ValueError("simulation id requires at least one simulated state")

    payload = {
        "config": config.canonical_payload(),
        "initial_state_fingerprint": initial_state.fingerprint(),
        "initial_state_id": initial_state.state_id,
        "missing_required_outputs": list(
            _normalize_unique_text_tuple(
                missing_required_outputs,
                "missing required output",
            )
        ),
        "rules": [rule.canonical_payload() for rule in _normalize_simulation_rules(rules)],
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": SIMULATION_SCHEMA_VERSION,
        "state_fingerprints": [state.fingerprint() for state in states],
        "state_ids": [state.state_id for state in states],
    }
    digest = _stable_sha256(payload)[:SIMULATION_ID_DIGEST_LENGTH]
    return f"simulation-{digest}"


def _dimensions_from_values(
    values: dict[str, float],
    units: dict[str, str],
    descriptions: dict[str, str],
) -> tuple[StateDimension, ...]:
    dimensions: list[StateDimension] = []

    for name in sorted(values):
        dimensions.append(
            StateDimension(
                name=name,
                value=values[name],
                unit=units.get(name, "value"),
                description=descriptions.get(name, "Simulated scalar value."),
                tags=("simulated",),
            )
        )

    return tuple(dimensions)


def _normalize_simulation_rules(
    rules: tuple[SimulationRule, ...],
) -> tuple[SimulationRule, ...]:
    if not rules:
        raise ValueError("simulation requires at least one rule")

    seen_rule_ids: set[str] = set()
    seen_targets: set[str] = set()
    normalized_rules: list[SimulationRule] = []

    for rule in rules:
        if rule.rule_id in seen_rule_ids:
            raise ValueError(f"duplicate simulation rule id: {rule.rule_id}")
        if rule.target in seen_targets:
            raise ValueError(f"duplicate simulation target: {rule.target}")
        seen_rule_ids.add(rule.rule_id)
        seen_targets.add(rule.target)
        normalized_rules.append(rule)

    return tuple(sorted(normalized_rules, key=lambda item: item.rule_id))


def _normalize_optional_float(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    return _require_finite_float(value, field_name)


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

"""Branching simulation runner for IX-BlackFox-WorldTwin.

Branching lets WorldTwin compare several bounded futures for the same scenario
without pretending that any branch is certain. Each branch remains deterministic,
replayable, fingerprinted, and anchored to the same scenario manifest.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.scenario import ScenarioManifest
from ix_blackfox_worldtwin.simulation import (
    SimulationConfig,
    SimulationResult,
    SimulationRule,
    run_deterministic_simulation,
)

BRANCHING_SCHEMA_VERSION = "branching-simulation-v1"
BRANCH_ID_DIGEST_LENGTH = 16


class BranchRankingDirection(StrEnum):
    """Direction used when ranking branch results by a final-state target."""

    ASCENDING = "ascending"
    DESCENDING = "descending"


@dataclass(frozen=True, slots=True)
class BranchDefinition:
    """A deterministic simulation branch for one scenario."""

    branch_id: str
    name: str
    description: str
    rules: tuple[SimulationRule, ...]
    config: SimulationConfig
    weight: float = 1.0
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    schema_version: str = BRANCHING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a branch definition."""

        object.__setattr__(self, "branch_id", _require_non_empty(self.branch_id, "branch id"))
        object.__setattr__(self, "name", _require_non_empty(self.name, "branch name"))
        object.__setattr__(
            self,
            "description",
            _require_non_empty(self.description, "branch description"),
        )
        object.__setattr__(self, "rules", _normalize_branch_rules(self.rules))
        object.__setattr__(self, "weight", _require_positive_float(self.weight, "branch weight"))
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_unique_text_tuple(self.evidence_ids, "evidence id"),
        )
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "branch tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "branch schema version"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "branch_id": self.branch_id,
            "config": self.config.canonical_payload(),
            "description": self.description,
            "evidence_ids": list(self.evidence_ids),
            "name": self.name,
            "rules": [rule.canonical_payload() for rule in self.rules],
            "schema_version": self.schema_version,
            "tags": list(self.tags),
            "weight": self.weight,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this branch definition."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class BranchSimulationResult:
    """Simulation result for one branch."""

    branch: BranchDefinition
    simulation: SimulationResult

    def __post_init__(self) -> None:
        """Validate that branch and simulation remain connected."""

        if not self.simulation.simulation_id:
            raise ValueError("branch simulation result requires a simulation id")

    @property
    def branch_id(self) -> str:
        """Return the branch id."""

        return self.branch.branch_id

    @property
    def scenario_id(self) -> str:
        """Return the scenario id from the simulation result."""

        return self.simulation.scenario_id

    def final_value(self, target: str) -> float:
        """Return a final simulated value by target name."""

        normalized_target = _require_non_empty(target, "branch target")
        values = self.simulation.predicted_values()
        if normalized_target not in values:
            raise KeyError(f"branch final target not found: {normalized_target}")
        return values[normalized_target]

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "branch": self.branch.canonical_payload(),
            "simulation_fingerprint": self.simulation.fingerprint(),
            "simulation_id": self.simulation.simulation_id,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this branch result."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class BranchComparison:
    """Aggregate comparison across deterministic scenario branches."""

    comparison_id: str
    scenario_id: str
    created_at: datetime
    results: tuple[BranchSimulationResult, ...]
    ranking_target: str
    ranking_direction: BranchRankingDirection
    created_by: str
    schema_version: str = BRANCHING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a branch comparison."""

        if not self.results:
            raise ValueError("branch comparison requires at least one result")

        scenario_ids = {result.scenario_id for result in self.results}
        if len(scenario_ids) != 1:
            raise ValueError("branch comparison results must share one scenario id")
        if self.scenario_id not in scenario_ids:
            raise ValueError("branch comparison scenario_id must match result scenario id")

        branch_ids = [result.branch_id for result in self.results]
        if len(set(branch_ids)) != len(branch_ids):
            raise ValueError("branch comparison contains duplicate branch ids")

        object.__setattr__(
            self,
            "comparison_id",
            _require_non_empty(self.comparison_id, "branch comparison id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "branch comparison created_at"),
        )
        object.__setattr__(
            self,
            "results",
            tuple(sorted(self.results, key=lambda result: result.branch_id)),
        )
        object.__setattr__(
            self,
            "ranking_target",
            _require_non_empty(self.ranking_target, "ranking target"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "branch schema version"),
        )

    def ranked_results(self) -> tuple[BranchSimulationResult, ...]:
        """Return branch results ranked by the configured final-state target."""

        reverse = self.ranking_direction is BranchRankingDirection.DESCENDING
        return tuple(
            sorted(
                self.results,
                key=lambda result: (result.final_value(self.ranking_target), result.branch_id),
                reverse=reverse,
            )
        )

    def leading_result(self) -> BranchSimulationResult:
        """Return the first branch after ranking."""

        return self.ranked_results()[0]

    def trailing_result(self) -> BranchSimulationResult:
        """Return the last branch after ranking."""

        return self.ranked_results()[-1]

    def branch_value_table(self) -> dict[str, float]:
        """Return branch ids mapped to the ranking target value."""

        return {
            result.branch_id: result.final_value(self.ranking_target)
            for result in self.ranked_results()
        }

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "comparison_id": self.comparison_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "ranking_direction": self.ranking_direction.value,
            "ranking_target": self.ranking_target,
            "result_fingerprints": [result.fingerprint() for result in self.results],
            "result_ids": [result.simulation.simulation_id for result in self.results],
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this branch comparison."""

        return _stable_sha256(self.canonical_payload())


def create_branch_definition(
    *,
    name: str,
    description: str,
    rules: tuple[SimulationRule, ...],
    config: SimulationConfig,
    weight: float = 1.0,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    branch_id: str | None = None,
) -> BranchDefinition:
    """Create a validated branch definition with a deterministic id by default."""

    normalized_name = _require_non_empty(name, "branch name")
    normalized_description = _require_non_empty(description, "branch description")
    normalized_rules = _normalize_branch_rules(rules)
    normalized_weight = _require_positive_float(weight, "branch weight")
    normalized_evidence_ids = _normalize_unique_text_tuple(evidence_ids, "evidence id")
    normalized_tags = _normalize_unique_text_tuple(tags, "branch tag")
    resolved_branch_id = branch_id or make_branch_id(
        name=normalized_name,
        description=normalized_description,
        rules=normalized_rules,
        config=config,
        weight=normalized_weight,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
    )

    return BranchDefinition(
        branch_id=resolved_branch_id,
        name=normalized_name,
        description=normalized_description,
        rules=normalized_rules,
        config=config,
        weight=normalized_weight,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
    )


def run_branching_simulation(
    *,
    scenario: ScenarioManifest,
    branches: tuple[BranchDefinition, ...],
    ranking_target: str,
    ranking_direction: BranchRankingDirection,
    created_at: datetime,
    created_by: str,
    comparison_id: str | None = None,
) -> BranchComparison:
    """Run several deterministic branches for the same scenario."""

    normalized_branches = _normalize_branches(branches)
    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "branch comparison created_at",
    )
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_target = _require_non_empty(ranking_target, "ranking target")

    results: list[BranchSimulationResult] = []
    for branch in normalized_branches:
        simulation = run_deterministic_simulation(
            scenario=scenario,
            rules=branch.rules,
            config=branch.config,
        )
        result = BranchSimulationResult(branch=branch, simulation=simulation)
        result.final_value(normalized_target)
        results.append(result)

    normalized_results = tuple(sorted(results, key=lambda result: result.branch_id))
    resolved_comparison_id = comparison_id or make_branch_comparison_id(
        scenario_id=scenario.scenario_id,
        created_at=normalized_created_at,
        results=normalized_results,
        ranking_target=normalized_target,
        ranking_direction=ranking_direction,
        created_by=normalized_created_by,
    )

    return BranchComparison(
        comparison_id=resolved_comparison_id,
        scenario_id=scenario.scenario_id,
        created_at=normalized_created_at,
        results=normalized_results,
        ranking_target=normalized_target,
        ranking_direction=ranking_direction,
        created_by=normalized_created_by,
    )


def make_branch_id(
    *,
    name: str,
    description: str,
    rules: tuple[SimulationRule, ...],
    config: SimulationConfig,
    weight: float = 1.0,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> str:
    """Create a deterministic branch id."""

    payload = {
        "config": config.canonical_payload(),
        "description": _require_non_empty(description, "branch description"),
        "evidence_ids": list(_normalize_unique_text_tuple(evidence_ids, "evidence id")),
        "name": _require_non_empty(name, "branch name"),
        "rules": [rule.canonical_payload() for rule in _normalize_branch_rules(rules)],
        "schema_version": BRANCHING_SCHEMA_VERSION,
        "tags": list(_normalize_unique_text_tuple(tags, "branch tag")),
        "weight": _require_positive_float(weight, "branch weight"),
    }
    digest = _stable_sha256(payload)[:BRANCH_ID_DIGEST_LENGTH]
    return f"branch-{digest}"


def make_branch_comparison_id(
    *,
    scenario_id: str,
    created_at: datetime,
    results: tuple[BranchSimulationResult, ...],
    ranking_target: str,
    ranking_direction: BranchRankingDirection,
    created_by: str,
) -> str:
    """Create a deterministic branch comparison id."""

    if not results:
        raise ValueError("branch comparison id requires at least one result")

    payload = {
        "created_at": _require_aware_utc_datetime(
            created_at,
            "branch comparison created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "ranking_direction": ranking_direction.value,
        "ranking_target": _require_non_empty(ranking_target, "ranking target"),
        "result_fingerprints": [
            result.fingerprint() for result in sorted(results, key=lambda item: item.branch_id)
        ],
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": BRANCHING_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:BRANCH_ID_DIGEST_LENGTH]
    return f"branch-comparison-{digest}"


def _normalize_branch_rules(rules: tuple[SimulationRule, ...]) -> tuple[SimulationRule, ...]:
    if not rules:
        raise ValueError("branch requires at least one simulation rule")

    seen_rule_ids: set[str] = set()
    seen_targets: set[str] = set()
    normalized_rules: list[SimulationRule] = []

    for rule in rules:
        if rule.rule_id in seen_rule_ids:
            raise ValueError(f"duplicate branch simulation rule id: {rule.rule_id}")
        if rule.target in seen_targets:
            raise ValueError(f"duplicate branch simulation target: {rule.target}")
        seen_rule_ids.add(rule.rule_id)
        seen_targets.add(rule.target)
        normalized_rules.append(rule)

    return tuple(sorted(normalized_rules, key=lambda item: item.rule_id))


def _normalize_branches(branches: tuple[BranchDefinition, ...]) -> tuple[BranchDefinition, ...]:
    if not branches:
        raise ValueError("branching simulation requires at least one branch")

    seen_branch_ids: set[str] = set()
    normalized_branches: list[BranchDefinition] = []

    for branch in branches:
        if branch.branch_id in seen_branch_ids:
            raise ValueError(f"duplicate branch id: {branch.branch_id}")
        seen_branch_ids.add(branch.branch_id)
        normalized_branches.append(branch)

    return tuple(sorted(normalized_branches, key=lambda item: item.branch_id))


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


def _require_positive_float(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    normalized_value = float(value)
    if normalized_value <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized_value


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()

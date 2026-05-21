"""Scenario validation gates for IX-BlackFox-WorldTwin.

Scenario manifests are not useful unless they can be rejected. This module
turns scenario structure into explicit validation results, so vague,
non-replayable, under-bounded, or authority-confused scenarios do not silently
move into simulation, prediction receipts, reality-delta scoring, or execution
evidence packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ix_blackfox_worldtwin.scenario import (
    ScenarioBoundaryKind,
    ScenarioManifest,
    ScenarioVariable,
    ScenarioVariableKind,
)
from ix_blackfox_worldtwin.state import WorldStateKind


class ScenarioValidationSeverity(StrEnum):
    """Severity levels returned by the scenario validation gate."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ScenarioValidationIssue:
    """A single scenario validation issue."""

    severity: ScenarioValidationSeverity
    code: str
    field: str
    message: str

    def __post_init__(self) -> None:
        """Validate and normalize a scenario validation issue."""

        object.__setattr__(self, "code", _require_non_empty(self.code, "issue code"))
        object.__setattr__(self, "field", _require_non_empty(self.field, "issue field"))
        object.__setattr__(self, "message", _require_non_empty(self.message, "issue message"))


@dataclass(frozen=True, slots=True)
class ScenarioValidationResult:
    """Validation result for a scenario manifest."""

    scenario_id: str
    issues: tuple[ScenarioValidationIssue, ...]

    def __post_init__(self) -> None:
        """Validate and normalize a scenario validation result."""

        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))

    @property
    def passed(self) -> bool:
        """Return True when the scenario has no validation errors."""

        return not self.has_errors

    @property
    def has_errors(self) -> bool:
        """Return True when the scenario has at least one validation error."""

        return any(issue.severity is ScenarioValidationSeverity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Return True when the scenario has at least one validation warning."""

        return any(issue.severity is ScenarioValidationSeverity.WARNING for issue in self.issues)

    def error_codes(self) -> tuple[str, ...]:
        """Return validation error codes in deterministic order."""

        return tuple(
            issue.code
            for issue in self.issues
            if issue.severity is ScenarioValidationSeverity.ERROR
        )

    def warning_codes(self) -> tuple[str, ...]:
        """Return validation warning codes in deterministic order."""

        return tuple(
            issue.code
            for issue in self.issues
            if issue.severity is ScenarioValidationSeverity.WARNING
        )


def validate_scenario_manifest(scenario: ScenarioManifest) -> ScenarioValidationResult:
    """Validate a scenario manifest before simulation or handoff."""

    issues: list[ScenarioValidationIssue] = []

    if scenario.initial_state.kind is not WorldStateKind.OBSERVED:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.ERROR,
                code="initial-state-not-observed",
                field="initial_state.kind",
                message="Scenario initial state must be observed reality, not simulated or predicted state.",
            )
        )

    if not scenario.replay_required:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.ERROR,
                code="replay-not-required",
                field="replay_required",
                message="Scenario replay must be required so prediction evidence can be reproduced.",
            )
        )

    if len(scenario.purpose) < 24:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.WARNING,
                code="purpose-too-short",
                field="purpose",
                message="Scenario purpose is short; reviewers may not understand what is being tested.",
            )
        )

    boundary_kinds = {boundary.kind for boundary in scenario.boundaries}
    if ScenarioBoundaryKind.HUMAN_REVIEW not in boundary_kinds:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.ERROR,
                code="missing-human-review-boundary",
                field="boundaries",
                message="Scenario must declare a human-review boundary before it can produce evidence.",
            )
        )

    if ScenarioBoundaryKind.TEMPORAL not in boundary_kinds:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.WARNING,
                code="missing-temporal-boundary",
                field="boundaries",
                message="Scenario has no explicit time boundary for prediction or replay.",
            )
        )

    if ScenarioBoundaryKind.SAFETY not in boundary_kinds and ScenarioBoundaryKind.POLICY not in boundary_kinds:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.WARNING,
                code="missing-safety-or-policy-boundary",
                field="boundaries",
                message="Scenario has no explicit safety or policy boundary.",
            )
        )

    if not any(boundary.is_hard_boundary for boundary in scenario.boundaries):
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.ERROR,
                code="no-hard-boundaries",
                field="boundaries",
                message="Scenario must include at least one hard boundary.",
            )
        )

    observed_dimension_names = set(scenario.initial_state.to_dimension_map())
    observed_variables = _variables_by_kind(
        scenario.variables,
        ScenarioVariableKind.OBSERVED,
    )
    for variable in observed_variables:
        if variable.name not in observed_dimension_names:
            issues.append(
                _issue(
                    severity=ScenarioValidationSeverity.ERROR,
                    code="observed-variable-missing-in-initial-state",
                    field=f"variables.{variable.name}",
                    message=(
                        f"Observed variable '{variable.name}' must appear as an initial-state "
                        "dimension."
                    ),
                )
            )

    controlled_variables = _variables_by_kind(
        scenario.variables,
        ScenarioVariableKind.CONTROLLED,
    )
    for variable in controlled_variables:
        if variable.minimum is None or variable.maximum is None:
            issues.append(
                _issue(
                    severity=ScenarioValidationSeverity.ERROR,
                    code="controlled-variable-unbounded",
                    field=f"variables.{variable.name}",
                    message=(
                        f"Controlled variable '{variable.name}' must declare both minimum and "
                        "maximum bounds."
                    ),
                )
            )

    disturbance_variables = _variables_by_kind(
        scenario.variables,
        ScenarioVariableKind.DISTURBANCE,
    )
    for variable in disturbance_variables:
        if variable.minimum is None or variable.maximum is None:
            issues.append(
                _issue(
                    severity=ScenarioValidationSeverity.WARNING,
                    code="disturbance-variable-unbounded",
                    field=f"variables.{variable.name}",
                    message=(
                        f"Disturbance variable '{variable.name}' has no complete numeric bounds."
                    ),
                )
            )

    if not scenario.required_output_names():
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.ERROR,
                code="no-required-outputs",
                field="expected_outputs",
                message="Scenario must define at least one required measurable output.",
            )
        )

    if not scenario.evidence_ids:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.WARNING,
                code="no-evidence-references",
                field="evidence_ids",
                message="Scenario has no evidence references for reviewer provenance.",
            )
        )

    if scenario.created_by.casefold() in {"unknown", "n/a", "none", "anonymous"}:
        issues.append(
            _issue(
                severity=ScenarioValidationSeverity.WARNING,
                code="weak-created-by",
                field="created_by",
                message="Scenario creator identity is weak and may reduce review confidence.",
            )
        )

    return ScenarioValidationResult(scenario_id=scenario.scenario_id, issues=tuple(issues))


def ensure_scenario_manifest_replayable(scenario: ScenarioManifest) -> ScenarioValidationResult:
    """Validate a scenario and raise ValueError when replay-blocking errors exist."""

    result = validate_scenario_manifest(scenario)
    if result.has_errors:
        joined_errors = "; ".join(
            f"{issue.code}: {issue.message}"
            for issue in result.issues
            if issue.severity is ScenarioValidationSeverity.ERROR
        )
        raise ValueError(f"scenario failed validation: {joined_errors}")

    return result


def _variables_by_kind(
    variables: tuple[ScenarioVariable, ...],
    kind: ScenarioVariableKind,
) -> tuple[ScenarioVariable, ...]:
    return tuple(variable for variable in variables if variable.kind is kind)


def _issue(
    *,
    severity: ScenarioValidationSeverity,
    code: str,
    field: str,
    message: str,
) -> ScenarioValidationIssue:
    return ScenarioValidationIssue(
        severity=severity,
        code=code,
        field=field,
        message=message,
    )


def _require_non_empty(value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")
    return normalized_value

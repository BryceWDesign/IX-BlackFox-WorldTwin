from __future__ import annotations

from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _observed_initial_state() -> worldtwin.WorldState:
    return worldtwin.create_observed_state(
        dimensions=(
            worldtwin.StateDimension("temperature", 72.0, "F"),
            worldtwin.StateDimension("load", 0.40, "ratio"),
        ),
        valid_at=_created_at(),
        created_at=_created_at(),
        source="sensor-feed-alpha",
    )


def _predicted_initial_state() -> worldtwin.WorldState:
    return worldtwin.create_predicted_state(
        dimensions=(
            worldtwin.StateDimension("temperature", 72.0, "F"),
            worldtwin.StateDimension("load", 0.40, "ratio"),
        ),
        valid_at=_created_at(),
        created_at=_created_at(),
        source="bad-predicted-start",
    )


def _valid_boundaries() -> tuple[worldtwin.ScenarioBoundary, ...]:
    return (
        worldtwin.ScenarioBoundary(
            name="time-window",
            kind=worldtwin.ScenarioBoundaryKind.TEMPORAL,
            description="Scenario may only project fifteen minutes ahead.",
        ),
        worldtwin.ScenarioBoundary(
            name="human-review",
            kind=worldtwin.ScenarioBoundaryKind.HUMAN_REVIEW,
            description="Scenario output remains review evidence, not authority.",
        ),
        worldtwin.ScenarioBoundary(
            name="safety-envelope",
            kind=worldtwin.ScenarioBoundaryKind.SAFETY,
            description="Scenario must not recommend bypassing safety limits.",
        ),
    )


def _weak_boundaries() -> tuple[worldtwin.ScenarioBoundary, ...]:
    return (
        worldtwin.ScenarioBoundary(
            name="time-window",
            kind=worldtwin.ScenarioBoundaryKind.TEMPORAL,
            description="Scenario may only project fifteen minutes ahead.",
            is_hard_boundary=False,
        ),
    )


def _valid_variables() -> tuple[worldtwin.ScenarioVariable, ...]:
    return (
        worldtwin.ScenarioVariable(
            name="temperature",
            kind=worldtwin.ScenarioVariableKind.OBSERVED,
            unit="F",
            description="Observed temperature channel.",
            minimum=-40.0,
            maximum=220.0,
        ),
        worldtwin.ScenarioVariable(
            name="load",
            kind=worldtwin.ScenarioVariableKind.CONTROLLED,
            unit="ratio",
            description="Normalized load command.",
            minimum=0.0,
            maximum=1.0,
        ),
        worldtwin.ScenarioVariable(
            name="risk_score",
            kind=worldtwin.ScenarioVariableKind.DERIVED,
            unit="score",
            description="Derived risk score.",
            minimum=0.0,
            maximum=1.0,
        ),
    )


def _valid_outputs() -> tuple[worldtwin.MeasurableOutput, ...]:
    return (
        worldtwin.MeasurableOutput(
            name="temperature",
            unit="F",
            description="Predicted temperature after the scenario window.",
        ),
        worldtwin.MeasurableOutput(
            name="risk_score",
            unit="score",
            description="Bounded scenario risk score.",
        ),
    )


def _valid_scenario() -> worldtwin.ScenarioManifest:
    return worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=_observed_initial_state(),
        boundaries=_valid_boundaries(),
        variables=_valid_variables(),
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("telemetry-evidence-alpha",),
        tags=("thermal", "bounded"),
    )


def test_valid_scenario_passes_without_errors_or_warnings() -> None:
    result = worldtwin.validate_scenario_manifest(_valid_scenario())

    assert result.passed is True
    assert result.has_errors is False
    assert result.has_warnings is False
    assert result.error_codes() == ()
    assert result.warning_codes() == ()


def test_ensure_scenario_manifest_replayable_returns_result_when_valid() -> None:
    result = worldtwin.ensure_scenario_manifest_replayable(_valid_scenario())

    assert result.passed is True
    assert result.scenario_id.startswith("scenario-")


def test_validation_rejects_predicted_initial_state() -> None:
    scenario = worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=_predicted_initial_state(),
        boundaries=_valid_boundaries(),
        variables=_valid_variables(),
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("telemetry-evidence-alpha",),
    )

    result = worldtwin.validate_scenario_manifest(scenario)

    assert result.passed is False
    assert "initial-state-not-observed" in result.error_codes()


def test_validation_rejects_missing_human_review_and_missing_hard_boundary() -> None:
    scenario = worldtwin.create_scenario_manifest(
        title="Weak scenario",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=_observed_initial_state(),
        boundaries=_weak_boundaries(),
        variables=_valid_variables(),
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("telemetry-evidence-alpha",),
    )

    result = worldtwin.validate_scenario_manifest(scenario)

    assert result.passed is False
    assert "missing-human-review-boundary" in result.error_codes()
    assert "no-hard-boundaries" in result.error_codes()
    assert "missing-safety-or-policy-boundary" in result.warning_codes()


def test_validation_rejects_non_replayable_scenario() -> None:
    scenario = worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=_observed_initial_state(),
        boundaries=_valid_boundaries(),
        variables=_valid_variables(),
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("telemetry-evidence-alpha",),
        replay_required=False,
    )

    result = worldtwin.validate_scenario_manifest(scenario)

    assert result.passed is False
    assert "replay-not-required" in result.error_codes()


def test_validation_rejects_missing_observed_variable_in_initial_state() -> None:
    variables = (
        worldtwin.ScenarioVariable(
            name="humidity",
            kind=worldtwin.ScenarioVariableKind.OBSERVED,
            unit="ratio",
            description="Observed humidity channel.",
            minimum=0.0,
            maximum=1.0,
        ),
        worldtwin.ScenarioVariable(
            name="load",
            kind=worldtwin.ScenarioVariableKind.CONTROLLED,
            unit="ratio",
            description="Normalized load command.",
            minimum=0.0,
            maximum=1.0,
        ),
    )
    scenario = worldtwin.create_scenario_manifest(
        title="Humidity missing from initial state",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside humidity review limits.",
        initial_state=_observed_initial_state(),
        boundaries=_valid_boundaries(),
        variables=variables,
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("telemetry-evidence-alpha",),
    )

    result = worldtwin.validate_scenario_manifest(scenario)

    assert result.passed is False
    assert "observed-variable-missing-in-initial-state" in result.error_codes()


def test_validation_rejects_unbounded_controlled_variable() -> None:
    variables = (
        worldtwin.ScenarioVariable(
            name="temperature",
            kind=worldtwin.ScenarioVariableKind.OBSERVED,
            unit="F",
            description="Observed temperature channel.",
        ),
        worldtwin.ScenarioVariable(
            name="load",
            kind=worldtwin.ScenarioVariableKind.CONTROLLED,
            unit="ratio",
            description="Normalized load command.",
        ),
    )
    scenario = worldtwin.create_scenario_manifest(
        title="Unbounded load command",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=_observed_initial_state(),
        boundaries=_valid_boundaries(),
        variables=variables,
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("telemetry-evidence-alpha",),
    )

    result = worldtwin.validate_scenario_manifest(scenario)

    assert result.passed is False
    assert "controlled-variable-unbounded" in result.error_codes()


def test_validation_warns_for_unbounded_disturbance_and_no_evidence() -> None:
    variables = _valid_variables() + (
        worldtwin.ScenarioVariable(
            name="ambient_disturbance",
            kind=worldtwin.ScenarioVariableKind.DISTURBANCE,
            unit="F",
            description="External temperature disturbance.",
        ),
    )
    scenario = worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=_observed_initial_state(),
        boundaries=_valid_boundaries(),
        variables=variables,
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )

    result = worldtwin.validate_scenario_manifest(scenario)

    assert result.passed is True
    assert "disturbance-variable-unbounded" in result.warning_codes()
    assert "no-evidence-references" in result.warning_codes()


def test_validation_warns_for_weak_purpose_and_weak_creator() -> None:
    scenario = worldtwin.create_scenario_manifest(
        title="Short purpose scenario",
        system_under_test="bench-controller-alpha",
        purpose="Too short.",
        initial_state=_observed_initial_state(),
        boundaries=_valid_boundaries(),
        variables=_valid_variables(),
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="unknown",
        evidence_ids=("telemetry-evidence-alpha",),
    )

    result = worldtwin.validate_scenario_manifest(scenario)

    assert result.passed is True
    assert "purpose-too-short" in result.warning_codes()
    assert "weak-created-by" in result.warning_codes()


def test_ensure_scenario_manifest_replayable_raises_on_errors() -> None:
    scenario = worldtwin.create_scenario_manifest(
        title="Weak scenario",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=_predicted_initial_state(),
        boundaries=_weak_boundaries(),
        variables=_valid_variables(),
        expected_outputs=_valid_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )

    with pytest.raises(ValueError, match="scenario failed validation"):
        worldtwin.ensure_scenario_manifest_replayable(scenario)

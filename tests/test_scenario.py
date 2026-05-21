from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _initial_state() -> worldtwin.WorldState:
    return worldtwin.create_observed_state(
        dimensions=(
            worldtwin.StateDimension("temperature", 72.0, "F"),
            worldtwin.StateDimension("load", 0.40, "ratio"),
        ),
        valid_at=_created_at(),
        created_at=_created_at(),
        source="sensor-feed-alpha",
    )


def _boundaries() -> tuple[worldtwin.ScenarioBoundary, ...]:
    return (
        worldtwin.ScenarioBoundary(
            name="time-window",
            kind=worldtwin.ScenarioBoundaryKind.TEMPORAL,
            description="Scenario may only project fifteen minutes ahead.",
        ),
        worldtwin.ScenarioBoundary(
            name="human-review",
            kind=worldtwin.ScenarioBoundaryKind.HUMAN_REVIEW,
            description="Scenario output must remain review evidence, not authority.",
        ),
    )


def _variables() -> tuple[worldtwin.ScenarioVariable, ...]:
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
    )


def _outputs() -> tuple[worldtwin.MeasurableOutput, ...]:
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


def test_scenario_manifest_records_bounded_test_question() -> None:
    scenario = worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether temperature remains inside review limits.",
        initial_state=_initial_state(),
        boundaries=_boundaries(),
        variables=_variables(),
        expected_outputs=_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("evidence-b", "evidence-a"),
        tags=("thermal", "bounded"),
    )

    assert scenario.scenario_id.startswith("scenario-")
    assert scenario.schema_version == worldtwin.SCENARIO_SCHEMA_VERSION
    assert scenario.title == "Thermal drift under bounded load"
    assert scenario.system_under_test == "bench-controller-alpha"
    assert scenario.purpose == "Estimate whether temperature remains inside review limits."
    assert scenario.initial_state.kind is worldtwin.WorldStateKind.OBSERVED
    assert scenario.created_at == _created_at()
    assert scenario.created_by == "worldtwin-test-suite"
    assert scenario.evidence_ids == ("evidence-a", "evidence-b")
    assert scenario.tags == ("bounded", "thermal")
    assert scenario.replay_required is True
    assert scenario.required_output_names() == ("risk_score", "temperature")


def test_scenario_manifest_fingerprint_is_deterministic_for_reordered_inputs() -> None:
    first = worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether temperature remains inside review limits.",
        initial_state=_initial_state(),
        boundaries=_boundaries(),
        variables=_variables(),
        expected_outputs=_outputs(),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("b", "a"),
        tags=("thermal", "bounded"),
    )
    second = worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether temperature remains inside review limits.",
        initial_state=_initial_state(),
        boundaries=tuple(reversed(_boundaries())),
        variables=tuple(reversed(_variables())),
        expected_outputs=tuple(reversed(_outputs())),
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("a", "b"),
        tags=("bounded", "thermal"),
    )

    assert first.scenario_id == second.scenario_id
    assert first.fingerprint() == second.fingerprint()


def test_scenario_manifest_normalizes_timezone_to_utc() -> None:
    local_time = datetime(2026, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=-8)))
    scenario = worldtwin.create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether temperature remains inside review limits.",
        initial_state=_initial_state(),
        boundaries=_boundaries(),
        variables=_variables(),
        expected_outputs=_outputs(),
        created_at=local_time,
        created_by="worldtwin-test-suite",
    )

    assert scenario.created_at == _created_at()


def test_scenario_manifest_rejects_naive_created_at() -> None:
    with pytest.raises(ValueError, match="scenario created_at must be timezone-aware"):
        worldtwin.create_scenario_manifest(
            title="Thermal drift under bounded load",
            system_under_test="bench-controller-alpha",
            purpose="Estimate whether temperature remains inside review limits.",
            initial_state=_initial_state(),
            boundaries=_boundaries(),
            variables=_variables(),
            expected_outputs=_outputs(),
            created_at=datetime(2026, 1, 1, 12, 0),
            created_by="worldtwin-test-suite",
        )


def test_scenario_manifest_requires_non_empty_collections() -> None:
    with pytest.raises(ValueError, match="scenario boundary list must not be empty"):
        worldtwin.create_scenario_manifest(
            title="Thermal drift under bounded load",
            system_under_test="bench-controller-alpha",
            purpose="Estimate whether temperature remains inside review limits.",
            initial_state=_initial_state(),
            boundaries=(),
            variables=_variables(),
            expected_outputs=_outputs(),
            created_at=_created_at(),
            created_by="worldtwin-test-suite",
        )


def test_scenario_manifest_rejects_duplicate_boundary_names() -> None:
    duplicate_boundaries = (
        worldtwin.ScenarioBoundary(
            name="time-window",
            kind=worldtwin.ScenarioBoundaryKind.TEMPORAL,
            description="First boundary.",
        ),
        worldtwin.ScenarioBoundary(
            name="time-window",
            kind=worldtwin.ScenarioBoundaryKind.POLICY,
            description="Second boundary.",
        ),
    )

    with pytest.raises(ValueError, match="duplicate scenario boundary: time-window"):
        worldtwin.create_scenario_manifest(
            title="Thermal drift under bounded load",
            system_under_test="bench-controller-alpha",
            purpose="Estimate whether temperature remains inside review limits.",
            initial_state=_initial_state(),
            boundaries=duplicate_boundaries,
            variables=_variables(),
            expected_outputs=_outputs(),
            created_at=_created_at(),
            created_by="worldtwin-test-suite",
        )


def test_scenario_variable_rejects_invalid_range() -> None:
    with pytest.raises(ValueError, match="variable minimum must be less than or equal to maximum"):
        worldtwin.ScenarioVariable(
            name="load",
            kind=worldtwin.ScenarioVariableKind.CONTROLLED,
            unit="ratio",
            description="Normalized load command.",
            minimum=1.0,
            maximum=0.0,
        )


def test_scenario_manifest_rejects_duplicate_evidence_ids_and_tags() -> None:
    with pytest.raises(ValueError, match="duplicate evidence id"):
        worldtwin.create_scenario_manifest(
            title="Thermal drift under bounded load",
            system_under_test="bench-controller-alpha",
            purpose="Estimate whether temperature remains inside review limits.",
            initial_state=_initial_state(),
            boundaries=_boundaries(),
            variables=_variables(),
            expected_outputs=_outputs(),
            created_at=_created_at(),
            created_by="worldtwin-test-suite",
            evidence_ids=("same", "same"),
        )

    with pytest.raises(ValueError, match="duplicate scenario tag"):
        worldtwin.create_scenario_manifest(
            title="Thermal drift under bounded load",
            system_under_test="bench-controller-alpha",
            purpose="Estimate whether temperature remains inside review limits.",
            initial_state=_initial_state(),
            boundaries=_boundaries(),
            variables=_variables(),
            expected_outputs=_outputs(),
            created_at=_created_at(),
            created_by="worldtwin-test-suite",
            tags=("same", "same"),
        )

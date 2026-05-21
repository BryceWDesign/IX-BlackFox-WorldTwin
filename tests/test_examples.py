from __future__ import annotations

import ix_blackfox_worldtwin as worldtwin


def test_thermal_drift_example_is_valid_and_replayable() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    validation = worldtwin.validate_scenario_manifest(scenario)

    assert scenario.title == "Thermal drift under bounded load"
    assert scenario.system_under_test == "bench-controller-alpha"
    assert scenario.created_at == worldtwin.EXAMPLE_CREATED_AT
    assert scenario.created_by == worldtwin.EXAMPLE_CREATOR
    assert scenario.replay_required is True
    assert validation.passed is True
    assert validation.error_codes() == ()
    assert validation.warning_codes() == ()


def test_resource_pressure_example_is_valid_and_replayable() -> None:
    scenario = worldtwin.build_resource_pressure_scenario()
    validation = worldtwin.ensure_scenario_manifest_replayable(scenario)

    assert scenario.title == "Resource pressure before agent-plan execution"
    assert scenario.system_under_test == "agent-workflow-runner-alpha"
    assert scenario.created_at == worldtwin.EXAMPLE_CREATED_AT
    assert scenario.created_by == worldtwin.EXAMPLE_CREATOR
    assert scenario.replay_required is True
    assert validation.passed is True
    assert validation.error_codes() == ()


def test_wave1_examples_are_deterministic_and_distinct() -> None:
    first_pass = worldtwin.get_wave1_example_scenarios()
    second_pass = worldtwin.get_wave1_example_scenarios()

    assert len(first_pass) == 2
    assert len(second_pass) == 2
    assert tuple(scenario.scenario_id for scenario in first_pass) == tuple(
        scenario.scenario_id for scenario in second_pass
    )
    assert tuple(scenario.fingerprint() for scenario in first_pass) == tuple(
        scenario.fingerprint() for scenario in second_pass
    )
    assert first_pass[0].scenario_id != first_pass[1].scenario_id


def test_wave1_examples_include_review_and_safety_or_policy_boundaries() -> None:
    for scenario in worldtwin.get_wave1_example_scenarios():
        boundary_kinds = {boundary.kind for boundary in scenario.boundaries}

        assert worldtwin.ScenarioBoundaryKind.HUMAN_REVIEW in boundary_kinds
        assert worldtwin.ScenarioBoundaryKind.TEMPORAL in boundary_kinds
        assert (
            worldtwin.ScenarioBoundaryKind.SAFETY in boundary_kinds
            or worldtwin.ScenarioBoundaryKind.POLICY in boundary_kinds
        )


def test_wave1_examples_expose_required_measurable_outputs() -> None:
    thermal, resource = worldtwin.get_wave1_example_scenarios()

    assert thermal.required_output_names() == ("risk_score", "temperature")
    assert resource.required_output_names() == (
        "cpu_load",
        "memory_pressure",
        "risk_score",
    )

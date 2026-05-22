from __future__ import annotations

from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _thermal_rules() -> tuple[worldtwin.SimulationRule, ...]:
    return (
        worldtwin.create_simulation_rule(
            target="temperature",
            delta_per_step=3.0,
            unit="F",
            description="Simple deterministic thermal drift.",
            minimum=-40.0,
            maximum=220.0,
            tags=("thermal",),
        ),
        worldtwin.create_simulation_rule(
            target="risk_score",
            delta_per_step=0.10,
            unit="score",
            description="Simple deterministic risk accumulation.",
            initial_value=0.0,
            minimum=0.0,
            maximum=1.0,
            clamp_to_bounds=True,
            tags=("risk",),
        ),
    )


def _config() -> worldtwin.SimulationConfig:
    return worldtwin.SimulationConfig(
        step_count=5,
        step_seconds=60,
        created_at=_created_at(),
        evidence_ids=("simulation-evidence-alpha",),
        tags=("ci-safe", "deterministic"),
    )


def test_simulation_rule_applies_delta_and_optional_clamp() -> None:
    unclamped = worldtwin.create_simulation_rule(
        target="temperature",
        delta_per_step=5.0,
        unit="F",
        description="Unclamped thermal drift.",
    )
    clamped = worldtwin.create_simulation_rule(
        target="risk_score",
        delta_per_step=0.50,
        unit="score",
        description="Clamped risk accumulation.",
        maximum=1.0,
        clamp_to_bounds=True,
    )

    assert unclamped.apply(72.0) == 77.0
    assert clamped.apply(0.75) == 1.0


def test_deterministic_simulation_runs_ci_safe_thermal_example() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    result = worldtwin.run_deterministic_simulation(
        scenario=scenario,
        rules=_thermal_rules(),
        config=_config(),
    )

    assert result.simulation_id.startswith("simulation-")
    assert result.schema_version == worldtwin.SIMULATION_SCHEMA_VERSION
    assert result.scenario_id == scenario.scenario_id
    assert result.step_count() == 5
    assert result.initial_state.state_id == scenario.initial_state.state_id
    assert result.final_state.kind is worldtwin.WorldStateKind.SIMULATED
    assert result.predicted_values()["temperature"] == 87.0
    assert result.predicted_values()["risk_score"] == 0.5
    assert result.missing_required_outputs == ()


def test_deterministic_simulation_fingerprint_is_replay_stable() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    first = worldtwin.run_deterministic_simulation(
        scenario=scenario,
        rules=_thermal_rules(),
        config=_config(),
    )
    second = worldtwin.run_deterministic_simulation(
        scenario=scenario,
        rules=tuple(reversed(_thermal_rules())),
        config=_config(),
    )

    assert first.simulation_id == second.simulation_id
    assert first.fingerprint() == second.fingerprint()
    assert first.predicted_values() == second.predicted_values()


def test_simulation_requires_all_required_outputs() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    incomplete_rules = (
        worldtwin.create_simulation_rule(
            target="temperature",
            delta_per_step=3.0,
            unit="F",
            description="Simple deterministic thermal drift.",
        ),
    )

    with pytest.raises(ValueError, match="simulation missing required outputs: risk_score"):
        worldtwin.run_deterministic_simulation(
            scenario=scenario,
            rules=incomplete_rules,
            config=_config(),
        )


def test_simulation_rejects_non_replayable_scenario() -> None:
    scenario = worldtwin.create_scenario_manifest(
        title="Non-replayable scenario",
        system_under_test="bench-controller-alpha",
        purpose="Estimate whether the controller remains inside thermal review limits.",
        initial_state=worldtwin.build_thermal_drift_scenario().initial_state,
        boundaries=worldtwin.build_thermal_drift_scenario().boundaries,
        variables=worldtwin.build_thermal_drift_scenario().variables,
        expected_outputs=worldtwin.build_thermal_drift_scenario().expected_outputs,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
        evidence_ids=("telemetry-evidence-alpha",),
        replay_required=False,
    )

    with pytest.raises(ValueError, match="scenario failed validation"):
        worldtwin.run_deterministic_simulation(
            scenario=scenario,
            rules=_thermal_rules(),
            config=_config(),
        )


def test_simulation_config_rejects_invalid_steps() -> None:
    with pytest.raises(ValueError, match="simulation step_count must be greater than zero"):
        worldtwin.SimulationConfig(
            step_count=0,
            step_seconds=60,
            created_at=_created_at(),
        )

    with pytest.raises(ValueError, match="simulation step_seconds must be greater than zero"):
        worldtwin.SimulationConfig(
            step_count=1,
            step_seconds=0,
            created_at=_created_at(),
        )


def test_simulation_rejects_duplicate_targets() -> None:
    first = worldtwin.create_simulation_rule(
        target="temperature",
        delta_per_step=3.0,
        unit="F",
        description="First rule.",
    )
    second = worldtwin.create_simulation_rule(
        target="temperature",
        delta_per_step=4.0,
        unit="F",
        description="Second rule.",
    )

    with pytest.raises(ValueError, match="duplicate simulation target: temperature"):
        worldtwin.run_deterministic_simulation(
            scenario=worldtwin.build_thermal_drift_scenario(),
            rules=(first, second),
            config=_config(),
        )


def test_simulation_rule_rejects_invalid_bounds() -> None:
    with pytest.raises(
        ValueError, match="simulation minimum must be less than or equal to maximum"
    ):
        worldtwin.create_simulation_rule(
            target="temperature",
            delta_per_step=1.0,
            unit="F",
            description="Invalid bounds.",
            minimum=10.0,
            maximum=0.0,
        )


def test_simulation_result_exposes_final_values_for_policy_constraints() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    result = worldtwin.run_deterministic_simulation(
        scenario=scenario,
        rules=_thermal_rules(),
        config=_config(),
    )
    constraint_set = worldtwin.create_constraint_set(
        rules=(
            worldtwin.create_constraint_rule(
                name="Temperature review limit",
                target="temperature",
                operator=worldtwin.ConstraintOperator.LESS_THAN_OR_EQUAL,
                severity=worldtwin.ConstraintSeverity.CRITICAL,
                description="Predicted temperature must stay under the review limit.",
                limit_value=180.0,
                is_hard=True,
            ),
            worldtwin.create_constraint_rule(
                name="Risk caution band",
                target="risk_score",
                operator=worldtwin.ConstraintOperator.LESS_THAN_OR_EQUAL,
                severity=worldtwin.ConstraintSeverity.WARNING,
                description="Risk score above this value should trigger caution.",
                limit_value=0.70,
                is_hard=False,
            ),
        ),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        scenario_id=scenario.scenario_id,
    )

    assert constraint_set.decision(result.predicted_values()) is worldtwin.ConstraintDecision.PASS

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _config() -> worldtwin.SimulationConfig:
    return worldtwin.SimulationConfig(
        step_count=5,
        step_seconds=60,
        created_at=_created_at(),
        tags=("branching", "ci-safe"),
    )


def _thermal_branch(
    *,
    name: str,
    temperature_delta: float,
    risk_delta: float,
) -> worldtwin.BranchDefinition:
    return worldtwin.create_branch_definition(
        name=name,
        description=f"Branch with {temperature_delta} F thermal drift per step.",
        rules=(
            worldtwin.create_simulation_rule(
                target="temperature",
                delta_per_step=temperature_delta,
                unit="F",
                description="Deterministic branch thermal drift.",
                minimum=-40.0,
                maximum=220.0,
            ),
            worldtwin.create_simulation_rule(
                target="risk_score",
                delta_per_step=risk_delta,
                unit="score",
                description="Deterministic branch risk accumulation.",
                initial_value=0.0,
                minimum=0.0,
                maximum=1.0,
                clamp_to_bounds=True,
            ),
        ),
        config=_config(),
        weight=1.0,
        evidence_ids=(f"evidence-{name.casefold().replace(' ', '-')}",),
        tags=("thermal", "branch"),
    )


def test_branch_definition_normalizes_and_fingerprints() -> None:
    branch = _thermal_branch(name="Low drift", temperature_delta=1.0, risk_delta=0.05)

    assert branch.branch_id.startswith("branch-")
    assert branch.schema_version == worldtwin.BRANCHING_SCHEMA_VERSION
    assert branch.name == "Low drift"
    assert branch.weight == 1.0
    assert branch.evidence_ids == ("evidence-low-drift",)
    assert branch.tags == ("branch", "thermal")
    assert branch.fingerprint() == branch.fingerprint()


def test_branch_definition_rejects_invalid_weight() -> None:
    with pytest.raises(ValueError, match="branch weight must be greater than zero"):
        worldtwin.create_branch_definition(
            name="Invalid weight",
            description="Invalid branch weight.",
            rules=_thermal_branch(
                name="Base branch",
                temperature_delta=1.0,
                risk_delta=0.05,
            ).rules,
            config=_config(),
            weight=0.0,
        )


def test_branching_simulation_ranks_ascending_temperature() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    low = _thermal_branch(name="Low drift", temperature_delta=1.0, risk_delta=0.05)
    high = _thermal_branch(name="High drift", temperature_delta=5.0, risk_delta=0.15)

    comparison = worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(high, low),
        ranking_target="temperature",
        ranking_direction=worldtwin.BranchRankingDirection.ASCENDING,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )

    assert comparison.comparison_id.startswith("branch-comparison-")
    assert comparison.scenario_id == scenario.scenario_id
    assert comparison.created_at == _created_at()
    assert comparison.created_by == "worldtwin-test-suite"
    assert comparison.ranking_target == "temperature"
    assert comparison.ranking_direction is worldtwin.BranchRankingDirection.ASCENDING
    assert comparison.leading_result().branch_id == low.branch_id
    assert comparison.trailing_result().branch_id == high.branch_id
    assert comparison.leading_result().final_value("temperature") == 77.0
    assert comparison.trailing_result().final_value("temperature") == 97.0


def test_branching_simulation_ranks_descending_risk_score() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    low = _thermal_branch(name="Low drift", temperature_delta=1.0, risk_delta=0.05)
    high = _thermal_branch(name="High drift", temperature_delta=5.0, risk_delta=0.15)

    comparison = worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(low, high),
        ranking_target="risk_score",
        ranking_direction=worldtwin.BranchRankingDirection.DESCENDING,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )

    assert comparison.leading_result().branch_id == high.branch_id
    assert comparison.trailing_result().branch_id == low.branch_id
    assert comparison.branch_value_table() == {
        high.branch_id: 0.75,
        low.branch_id: 0.25,
    }


def test_branching_comparison_fingerprint_is_replay_stable() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    low = _thermal_branch(name="Low drift", temperature_delta=1.0, risk_delta=0.05)
    high = _thermal_branch(name="High drift", temperature_delta=5.0, risk_delta=0.15)

    first = worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(high, low),
        ranking_target="temperature",
        ranking_direction=worldtwin.BranchRankingDirection.ASCENDING,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )
    second = worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(low, high),
        ranking_target="temperature",
        ranking_direction=worldtwin.BranchRankingDirection.ASCENDING,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )

    assert first.comparison_id == second.comparison_id
    assert first.fingerprint() == second.fingerprint()
    assert first.branch_value_table() == second.branch_value_table()


def test_branching_rejects_duplicate_branch_ids() -> None:
    branch = _thermal_branch(name="Low drift", temperature_delta=1.0, risk_delta=0.05)

    with pytest.raises(ValueError, match=f"duplicate branch id: {branch.branch_id}"):
        worldtwin.run_branching_simulation(
            scenario=worldtwin.build_thermal_drift_scenario(),
            branches=(branch, branch),
            ranking_target="temperature",
            ranking_direction=worldtwin.BranchRankingDirection.ASCENDING,
            created_at=_created_at(),
            created_by="worldtwin-test-suite",
        )


def test_branching_rejects_missing_ranking_target() -> None:
    branch = _thermal_branch(name="Low drift", temperature_delta=1.0, risk_delta=0.05)

    with pytest.raises(KeyError, match="branch final target not found: unknown"):
        worldtwin.run_branching_simulation(
            scenario=worldtwin.build_thermal_drift_scenario(),
            branches=(branch,),
            ranking_target="unknown",
            ranking_direction=worldtwin.BranchRankingDirection.ASCENDING,
            created_at=_created_at(),
            created_by="worldtwin-test-suite",
        )


def test_branching_rejects_duplicate_rule_targets_inside_branch() -> None:
    first = worldtwin.create_simulation_rule(
        target="temperature",
        delta_per_step=1.0,
        unit="F",
        description="First duplicate target rule.",
    )
    second = worldtwin.create_simulation_rule(
        target="temperature",
        delta_per_step=2.0,
        unit="F",
        description="Second duplicate target rule.",
    )

    with pytest.raises(ValueError, match="duplicate branch simulation target: temperature"):
        worldtwin.create_branch_definition(
            name="Duplicate target branch",
            description="Branch should reject duplicate rule targets.",
            rules=(first, second),
            config=_config(),
        )


def test_branch_comparison_rejects_mismatched_scenario_id_when_constructed_directly() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    branch = _thermal_branch(name="Low drift", temperature_delta=1.0, risk_delta=0.05)
    comparison = worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(branch,),
        ranking_target="temperature",
        ranking_direction=worldtwin.BranchRankingDirection.ASCENDING,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )

    with pytest.raises(ValueError, match="branch comparison scenario_id must match result scenario id"):
        worldtwin.BranchComparison(
            comparison_id="branch-comparison-manual",
            scenario_id="scenario-other",
            created_at=_created_at(),
            results=comparison.results,
            ranking_target="temperature",
            ranking_direction=worldtwin.BranchRankingDirection.ASCENDING,
            created_by="worldtwin-test-suite",
        )

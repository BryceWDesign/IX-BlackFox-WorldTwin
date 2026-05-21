from __future__ import annotations

from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _rules() -> tuple[worldtwin.SimulationRule, ...]:
    return (
        worldtwin.create_simulation_rule(
            target="temperature",
            delta_per_step=3.0,
            unit="F",
            description="Simple deterministic thermal drift.",
            minimum=-40.0,
            maximum=220.0,
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
        ),
    )


def _config() -> worldtwin.SimulationConfig:
    return worldtwin.SimulationConfig(
        step_count=5,
        step_seconds=60,
        created_at=_created_at(),
        tags=("reproducibility", "ci-safe"),
    )


def _simulation() -> worldtwin.SimulationResult:
    return worldtwin.run_deterministic_simulation(
        scenario=worldtwin.build_thermal_drift_scenario(),
        rules=_rules(),
        config=_config(),
    )


def test_reproducibility_manifest_records_scenario_and_simulation_artifacts() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    simulation = _simulation()

    manifest = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
        notes=("replay before receipt generation",),
    )

    assert manifest.manifest_id.startswith("reproducibility-manifest-")
    assert manifest.schema_version == worldtwin.REPRODUCIBILITY_SCHEMA_VERSION
    assert manifest.scenario_id == scenario.scenario_id
    assert manifest.created_at == _created_at()
    assert manifest.created_by == "worldtwin-replay-gate"
    assert manifest.notes == ("replay before receipt generation",)
    assert manifest.artifact_table()[scenario.scenario_id] == scenario.fingerprint()
    assert manifest.artifact_table()[simulation.simulation_id] == simulation.fingerprint()


def test_reproducibility_check_passes_when_artifacts_match_manifest() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    simulation = _simulation()
    manifest = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
    )

    check = worldtwin.check_reproducibility(
        manifest=manifest,
        current_artifacts=manifest.artifacts,
        checked_at=_created_at(),
        checked_by="worldtwin-replay-gate",
    )

    assert check.check_id.startswith("reproducibility-check-")
    assert check.status is worldtwin.ReproducibilityStatus.PASS
    assert check.passed is True
    assert check.mismatches == ()
    assert check.missing_artifacts == ()


def test_reproducibility_check_fails_when_artifact_is_missing() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    simulation = _simulation()
    manifest = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
    )

    check = worldtwin.check_reproducibility(
        manifest=manifest,
        current_artifacts=(manifest.artifacts[0],),
        checked_at=_created_at(),
        checked_by="worldtwin-replay-gate",
    )

    assert check.status is worldtwin.ReproducibilityStatus.FAIL
    assert check.passed is False
    assert check.mismatches == ()
    assert check.missing_artifacts == (simulation.simulation_id,)


def test_reproducibility_check_fails_when_artifact_fingerprint_changes() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    simulation = _simulation()
    manifest = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
    )
    changed_artifact = worldtwin.ReproducibilityArtifact(
        artifact_id=simulation.simulation_id,
        artifact_type="simulation",
        fingerprint="changed-fingerprint",
        source="deterministic-simulation",
    )

    check = worldtwin.check_reproducibility(
        manifest=manifest,
        current_artifacts=(manifest.artifacts[0], changed_artifact),
        checked_at=_created_at(),
        checked_by="worldtwin-replay-gate",
    )

    assert check.status is worldtwin.ReproducibilityStatus.FAIL
    assert check.passed is False
    assert check.mismatches == (simulation.simulation_id,)
    assert check.missing_artifacts == ()


def test_reproducibility_manifest_accepts_branch_and_risk_artifacts() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    branch = worldtwin.create_branch_definition(
        name="Replay branch",
        description="Replay branch for reproducibility checks.",
        rules=_rules(),
        config=_config(),
    )
    branch_comparison = worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(branch,),
        ranking_target="risk_score",
        ranking_direction=worldtwin.BranchRankingDirection.DESCENDING,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
    )
    risk_comparison = worldtwin.compare_branch_risks(
        comparison=branch_comparison,
        target_weights={"risk_score": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
    )
    simulation = branch_comparison.results[0].simulation

    manifest = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        branch_comparison=branch_comparison,
        risk_comparison=risk_comparison,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
    )

    artifact_types = tuple(artifact.artifact_type for artifact in manifest.artifacts)

    assert artifact_types == (
        "branch-comparison",
        "risk-comparison",
        "scenario",
        "simulation",
    )
    assert manifest.artifact_table()[branch_comparison.comparison_id] == (
        branch_comparison.fingerprint()
    )
    assert manifest.artifact_table()[risk_comparison.comparison_id] == risk_comparison.fingerprint()


def test_reproducibility_manifest_rejects_scenario_mismatch() -> None:
    scenario = worldtwin.build_resource_pressure_scenario()
    simulation = _simulation()

    with pytest.raises(ValueError, match="simulation scenario_id must match manifest scenario_id"):
        worldtwin.create_reproducibility_manifest(
            scenario=scenario,
            simulation=simulation,
            created_at=_created_at(),
            created_by="worldtwin-replay-gate",
        )


def test_reproducibility_check_rejects_status_mismatch_when_constructed_directly() -> None:
    with pytest.raises(
        ValueError,
        match="reproducibility status must match mismatch and missing-artifact state",
    ):
        worldtwin.ReproducibilityCheck(
            check_id="reproducibility-check-manual",
            manifest_id="reproducibility-manifest-manual",
            status=worldtwin.ReproducibilityStatus.PASS,
            checked_at=_created_at(),
            checked_by="worldtwin-replay-gate",
            mismatches=("artifact-a",),
        )


def test_reproducibility_manifest_fingerprint_is_replay_stable() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    simulation = _simulation()

    first = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
        notes=("b", "a"),
    )
    second = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
        notes=("a", "b"),
    )

    assert first.manifest_id == second.manifest_id
    assert first.fingerprint() == second.fingerprint()

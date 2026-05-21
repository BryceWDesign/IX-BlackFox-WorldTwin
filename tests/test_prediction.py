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


def _simulation() -> worldtwin.SimulationResult:
    return worldtwin.run_deterministic_simulation(
        scenario=worldtwin.build_thermal_drift_scenario(),
        rules=_rules(),
        config=worldtwin.SimulationConfig(
            step_count=5,
            step_seconds=60,
            created_at=_created_at(),
        ),
    )


def _confidence(confidence: float = 0.80) -> worldtwin.ConfidenceAssessment:
    return worldtwin.create_confidence_assessment(
        target_id=_simulation().simulation_id,
        confidence=confidence,
        rationale="Simulation is deterministic and scenario-bounded.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
    )


def _policy() -> worldtwin.PolicyEvaluation:
    scenario = worldtwin.build_thermal_drift_scenario()
    return worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
    )


def test_prediction_result_packages_simulation_and_confidence_evidence() -> None:
    simulation = _simulation()
    prediction = worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(),
    )

    assert prediction.prediction_id.startswith("prediction-")
    assert prediction.schema_version == worldtwin.PREDICTION_SCHEMA_VERSION
    assert prediction.scenario_id == simulation.scenario_id
    assert prediction.simulation_id == simulation.simulation_id
    assert prediction.final_state.state_id == simulation.final_state.state_id
    assert prediction.final_values["temperature"] == 87.0
    assert prediction.confidence_tier is worldtwin.ConfidenceTier.HIGH
    assert prediction.disposition is worldtwin.PredictionDisposition.ACCEPT
    assert prediction.blocks_execution_review is False
    assert prediction.finding_codes() == (
        "confidence-high",
        "policy-not-attached",
        "reproducibility-not-attached",
        "risk-not-attached",
    )


def test_prediction_result_requires_review_for_low_confidence() -> None:
    prediction = worldtwin.create_prediction_result(
        simulation=_simulation(),
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(confidence=0.30),
    )

    assert prediction.confidence_tier is worldtwin.ConfidenceTier.LOW
    assert prediction.disposition is worldtwin.PredictionDisposition.REVIEW
    assert prediction.requires_human_review is True


def test_prediction_result_uses_policy_caution_when_policy_is_not_clean() -> None:
    prediction = worldtwin.create_prediction_result(
        simulation=_simulation(),
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(),
        policy_evaluation=_policy(),
    )

    assert prediction.disposition is worldtwin.PredictionDisposition.CAUTION
    assert prediction.requires_human_review is True
    assert "policy-caution" in prediction.finding_codes()


def test_prediction_result_uses_risk_quarantine_when_risk_profile_requires_it() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    high_risk_branch = worldtwin.create_branch_definition(
        name="High risk branch",
        description="A branch that drives risk score into quarantine territory.",
        rules=(
            worldtwin.create_simulation_rule(
                target="temperature",
                delta_per_step=3.0,
                unit="F",
                description="Simple deterministic thermal drift.",
            ),
            worldtwin.create_simulation_rule(
                target="risk_score",
                delta_per_step=0.18,
                unit="score",
                description="High risk accumulation.",
                initial_value=0.0,
                maximum=1.0,
                clamp_to_bounds=True,
            ),
        ),
        config=worldtwin.SimulationConfig(
            step_count=5,
            step_seconds=60,
            created_at=_created_at(),
        ),
    )
    comparison = worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(high_risk_branch,),
        ranking_target="risk_score",
        ranking_direction=worldtwin.BranchRankingDirection.DESCENDING,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )
    risk_comparison = worldtwin.compare_branch_risks(
        comparison=comparison,
        target_weights={"risk_score": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )

    prediction = worldtwin.create_prediction_result(
        simulation=comparison.results[0].simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=worldtwin.create_confidence_assessment(
            target_id=comparison.results[0].simulation.simulation_id,
            confidence=0.80,
            rationale="Simulation is deterministic and scenario-bounded.",
            created_at=_created_at(),
            assessor="worldtwin-confidence-gate",
        ),
        risk_comparison=risk_comparison,
    )

    assert prediction.disposition is worldtwin.PredictionDisposition.QUARANTINE
    assert prediction.blocks_execution_review is True
    assert "risk-quarantine" in prediction.finding_codes()


def test_prediction_result_attaches_reproducibility_manifest() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    simulation = _simulation()
    manifest = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
    )

    prediction = worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(),
        reproducibility_manifest=manifest,
    )

    assert prediction.reproducibility_manifest_id == manifest.manifest_id
    assert "reproducibility-attached" in prediction.finding_codes()


def test_prediction_result_fingerprint_is_replay_stable() -> None:
    simulation = _simulation()
    first = worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(),
    )
    second = worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(),
    )

    assert first.prediction_id == second.prediction_id
    assert first.fingerprint() == second.fingerprint()


def test_prediction_result_rejects_mismatched_risk_profile() -> None:
    simulation = _simulation()
    risk_factor = worldtwin.create_risk_factor(
        target="risk_score",
        observed_value=0.10,
        weight=1.0,
        rationale="Manual mismatched risk factor.",
    )
    mismatched_profile = worldtwin.RiskProfile(
        profile_id="risk-profile-manual",
        scenario_id=simulation.scenario_id,
        branch_id="branch-manual",
        simulation_id="simulation-other",
        aggregate_score=0.10,
        severity=worldtwin.RiskSeverity.INFO,
        recommendation=worldtwin.RiskRecommendation.ACCEPT,
        factors=(risk_factor,),
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )

    with pytest.raises(
        ValueError,
        match="risk profile simulation_id must match prediction simulation_id",
    ):
        worldtwin.create_prediction_result(
            simulation=simulation,
            created_at=_created_at(),
            created_by="worldtwin-prediction-gate",
            confidence_assessment=_confidence(),
            risk_profile=mismatched_profile,
        )


def test_prediction_result_rejects_empty_findings_when_constructed_directly() -> None:
    simulation = _simulation()

    with pytest.raises(ValueError, match="prediction result requires at least one finding"):
        worldtwin.PredictionResult(
            prediction_id="prediction-manual",
            scenario_id=simulation.scenario_id,
            source_kind=worldtwin.PredictionSourceKind.DETERMINISTIC_SIMULATION,
            final_state=simulation.final_state,
            simulation_id=simulation.simulation_id,
            created_at=_created_at(),
            created_by="worldtwin-prediction-gate",
            disposition=worldtwin.PredictionDisposition.ACCEPT,
            confidence_tier=worldtwin.ConfidenceTier.HIGH,
            findings=(),
        )

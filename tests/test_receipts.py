from __future__ import annotations

from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _simulation() -> worldtwin.SimulationResult:
    return worldtwin.run_deterministic_simulation(
        scenario=worldtwin.build_thermal_drift_scenario(),
        rules=(
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
        ),
        config=worldtwin.SimulationConfig(
            step_count=5,
            step_seconds=60,
            created_at=_created_at(),
        ),
    )


def _confidence(confidence: float = 0.80) -> worldtwin.ConfidenceAssessment:
    simulation = _simulation()
    return worldtwin.create_confidence_assessment(
        target_id=simulation.simulation_id,
        confidence=confidence,
        rationale="Simulation is deterministic and scenario-bounded.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
    )


def _prediction(confidence: float = 0.80) -> worldtwin.PredictionResult:
    return worldtwin.create_prediction_result(
        simulation=_simulation(),
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(confidence=confidence),
    )


def test_prediction_receipt_records_prediction_and_final_state_artifacts() -> None:
    prediction = _prediction()
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
        notes=("receipt before handoff",),
    )

    assert receipt.receipt_id.startswith("prediction-receipt-")
    assert receipt.schema_version == worldtwin.RECEIPT_SCHEMA_VERSION
    assert receipt.prediction_id == prediction.prediction_id
    assert receipt.scenario_id == prediction.scenario_id
    assert receipt.simulation_id == prediction.simulation_id
    assert receipt.created_at == _created_at()
    assert receipt.created_by == "worldtwin-receipt-gate"
    assert receipt.review_decision is worldtwin.ReceiptReviewDecision.RECORD_ONLY
    assert receipt.prediction_disposition is worldtwin.PredictionDisposition.ACCEPT
    assert receipt.final_state_id == prediction.final_state.state_id
    assert receipt.final_state_fingerprint == prediction.final_state.fingerprint()
    assert receipt.finding_codes == prediction.finding_codes()
    assert receipt.notes == ("receipt before handoff",)
    assert receipt.artifact_table()[prediction.prediction_id] == prediction.fingerprint()
    assert receipt.artifact_table()[prediction.final_state.state_id] == (
        prediction.final_state.fingerprint()
    )


def test_prediction_receipt_requires_human_review_for_low_confidence_prediction() -> None:
    prediction = _prediction(confidence=0.30)
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
    )

    assert prediction.disposition is worldtwin.PredictionDisposition.REVIEW
    assert receipt.review_decision is worldtwin.ReceiptReviewDecision.HUMAN_REVIEW_REQUIRED
    assert receipt.requires_human_review is True
    assert receipt.blocks_execution_review is False


def test_prediction_receipt_blocks_denied_or_quarantined_prediction() -> None:
    simulation = _simulation()
    factor = worldtwin.create_risk_factor(
        target="risk_score",
        observed_value=0.95,
        weight=1.0,
        rationale="Manual high risk factor.",
    )
    profile = worldtwin.RiskProfile(
        profile_id="risk-profile-manual",
        scenario_id=simulation.scenario_id,
        branch_id="branch-manual",
        simulation_id=simulation.simulation_id,
        aggregate_score=0.95,
        severity=worldtwin.RiskSeverity.CRITICAL,
        recommendation=worldtwin.RiskRecommendation.QUARANTINE,
        factors=(factor,),
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )
    prediction = worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=_confidence(),
        risk_profile=profile,
    )
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
    )

    assert prediction.disposition is worldtwin.PredictionDisposition.QUARANTINE
    assert receipt.review_decision is worldtwin.ReceiptReviewDecision.EXECUTION_REVIEW_BLOCKED
    assert receipt.requires_human_review is True
    assert receipt.blocks_execution_review is True


def test_prediction_receipt_attaches_reproducibility_manifest_artifact() -> None:
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

    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
        reproducibility_manifest=manifest,
    )

    assert receipt.artifact_table()[manifest.manifest_id] == manifest.fingerprint()


def test_prediction_receipt_rejects_mismatched_reproducibility_manifest() -> None:
    prediction = _prediction()
    manifest = worldtwin.ReproducibilityManifest(
        manifest_id="reproducibility-manifest-other",
        scenario_id=prediction.scenario_id,
        created_at=_created_at(),
        created_by="worldtwin-replay-gate",
        artifacts=(
            worldtwin.ReproducibilityArtifact(
                artifact_id="artifact-a",
                artifact_type="manual",
                fingerprint="fingerprint-a",
                source="test",
            ),
        ),
        replay_command="python -m ix_blackfox_worldtwin.cli run-demo",
    )

    with pytest.raises(
        ValueError,
        match="reproducibility manifest id must match prediction reproducibility_manifest_id",
    ):
        worldtwin.create_prediction_receipt(
            prediction=prediction,
            created_at=_created_at(),
            created_by="worldtwin-receipt-gate",
            reproducibility_manifest=manifest,
        )


def test_prediction_receipt_fingerprint_is_replay_stable() -> None:
    prediction = _prediction()
    first = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
        notes=("b", "a"),
    )
    second = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
        notes=("a", "b"),
    )

    assert first.receipt_id == second.receipt_id
    assert first.fingerprint() == second.fingerprint()


def test_prediction_receipt_rejects_duplicate_additional_artifact() -> None:
    prediction = _prediction()
    duplicate = worldtwin.ReceiptArtifact(
        artifact_id=prediction.prediction_id,
        artifact_type="duplicate",
        fingerprint="duplicate-fingerprint",
        source="test",
    )

    with pytest.raises(ValueError, match=f"duplicate receipt artifact id: {prediction.prediction_id}"):
        worldtwin.create_prediction_receipt(
            prediction=prediction,
            created_at=_created_at(),
            created_by="worldtwin-receipt-gate",
            additional_artifacts=(duplicate,),
        )


def test_prediction_receipt_rejects_empty_artifacts_when_constructed_directly() -> None:
    prediction = _prediction()

    with pytest.raises(ValueError, match="prediction receipt requires at least one artifact"):
        worldtwin.PredictionReceipt(
            receipt_id="prediction-receipt-manual",
            prediction_id=prediction.prediction_id,
            scenario_id=prediction.scenario_id,
            simulation_id=prediction.simulation_id,
            created_at=_created_at(),
            created_by="worldtwin-receipt-gate",
            review_decision=worldtwin.ReceiptReviewDecision.RECORD_ONLY,
            prediction_disposition=prediction.disposition,
            final_state_id=prediction.final_state.state_id,
            final_state_fingerprint=prediction.final_state.fingerprint(),
            artifacts=(),
            finding_codes=prediction.finding_codes(),
        )

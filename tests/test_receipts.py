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


def _prediction(
    *,
    confidence_value: float = 0.80,
    policy_evaluation: worldtwin.PolicyEvaluation | None = None,
) -> worldtwin.PredictionResult:
    simulation = _simulation()
    confidence = worldtwin.create_confidence_assessment(
        target_id=simulation.simulation_id,
        confidence=confidence_value,
        rationale="Simulation is deterministic and scenario-bounded.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
    )
    return worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=confidence,
        policy_evaluation=policy_evaluation,
    )


def _policy_deny() -> worldtwin.PolicyEvaluation:
    scenario = worldtwin.build_thermal_drift_scenario()
    assumption = worldtwin.create_assumption_record(
        name="Missing telemetry authentication",
        category=worldtwin.AssumptionCategory.DATA_QUALITY,
        statement="Telemetry identity has not been authenticated.",
        confidence=0.80,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.CRITICAL,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        required_evidence=(worldtwin.RequiredEvidence("telemetry authentication receipt"),),
    )
    ledger = worldtwin.create_assumption_ledger(
        assumptions=(assumption,),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        scenario_id=scenario.scenario_id,
    )

    return worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=ledger,
    )


def test_prediction_receipt_records_accepted_prediction_without_execution_authority() -> None:
    prediction = _prediction()
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
        notes=("manual review packet",),
    )

    assert receipt.receipt_id.startswith("prediction-receipt-")
    assert receipt.schema_version == worldtwin.RECEIPT_SCHEMA_VERSION
    assert receipt.prediction_id == prediction.prediction_id
    assert receipt.scenario_id == prediction.scenario_id
    assert receipt.simulation_id == prediction.simulation_id
    assert receipt.review_decision is worldtwin.ReceiptReviewDecision.RECORD_ONLY
    assert receipt.requires_human_authority is True
    assert receipt.allowed_for_automatic_execution is False
    assert receipt.ready_for_human_review is True
    assert receipt.blocks_execution_review is False
    assert receipt.artifact_ids() == (
        prediction.final_state.state_id,
        prediction.prediction_id,
    )
    assert receipt.notes == ("manual review packet",)


def test_prediction_receipt_requires_human_review_for_low_confidence_prediction() -> None:
    prediction = _prediction(confidence_value=0.30)
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
    )

    assert prediction.disposition is worldtwin.PredictionDisposition.REVIEW
    assert receipt.review_decision is worldtwin.ReceiptReviewDecision.HUMAN_REVIEW_REQUIRED
    assert receipt.ready_for_human_review is True
    assert receipt.blocks_execution_review is False


def test_prediction_receipt_blocks_denied_prediction() -> None:
    policy = _policy_deny()
    prediction = _prediction(policy_evaluation=policy)
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
    )

    assert prediction.disposition is worldtwin.PredictionDisposition.DENY
    assert receipt.review_decision is worldtwin.ReceiptReviewDecision.BLOCKED
    assert receipt.blocks_execution_review is True
    assert receipt.ready_for_human_review is False


def test_prediction_receipt_includes_core_artifacts_and_optional_context() -> None:
    prediction = _prediction()
    extra_artifact = worldtwin.ReceiptArtifact(
        artifact_id="policy-alpha",
        artifact_type="policy-evaluation",
        fingerprint="fingerprint-policy-alpha",
        source="policy",
    )
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
        artifacts=(extra_artifact,),
    )

    artifact_types = tuple(artifact.artifact_type for artifact in receipt.artifacts)

    assert artifact_types == (
        "policy-evaluation",
        "prediction-final-state",
        "prediction-result",
    )
    assert receipt.artifact_table()["policy-alpha"] == "fingerprint-policy-alpha"


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


def test_prediction_receipt_rejects_duplicate_artifacts() -> None:
    artifact = worldtwin.ReceiptArtifact(
        artifact_id="artifact-alpha",
        artifact_type="manual",
        fingerprint="fingerprint-alpha",
        source="test",
    )

    with pytest.raises(ValueError, match="duplicate receipt artifact id: artifact-alpha"):
        worldtwin.create_prediction_receipt(
            prediction=_prediction(),
            created_at=_created_at(),
            created_by="worldtwin-receipt-gate",
            artifacts=(artifact, artifact),
        )


def test_prediction_receipt_rejects_automatic_execution_when_constructed_directly() -> None:
    prediction = _prediction()
    artifact = worldtwin.ReceiptArtifact(
        artifact_id=prediction.prediction_id,
        artifact_type="prediction-result",
        fingerprint=prediction.fingerprint(),
        source="prediction",
    )

    with pytest.raises(
        ValueError,
        match="prediction receipt must never allow automatic execution",
    ):
        worldtwin.PredictionReceipt(
            receipt_id="prediction-receipt-manual",
            prediction_id=prediction.prediction_id,
            scenario_id=prediction.scenario_id,
            simulation_id=prediction.simulation_id,
            prediction_disposition=prediction.disposition,
            review_decision=worldtwin.ReceiptReviewDecision.RECORD_ONLY,
            created_at=_created_at(),
            created_by="worldtwin-receipt-gate",
            artifacts=(artifact,),
            allowed_for_automatic_execution=True,
        )


def test_prediction_receipt_rejects_decision_mismatch_when_constructed_directly() -> None:
    prediction = _prediction(policy_evaluation=_policy_deny())
    artifact = worldtwin.ReceiptArtifact(
        artifact_id=prediction.prediction_id,
        artifact_type="prediction-result",
        fingerprint=prediction.fingerprint(),
        source="prediction",
    )

    with pytest.raises(
        ValueError,
        match="receipt review decision must match prediction disposition",
    ):
        worldtwin.PredictionReceipt(
            receipt_id="prediction-receipt-manual",
            prediction_id=prediction.prediction_id,
            scenario_id=prediction.scenario_id,
            simulation_id=prediction.simulation_id,
            prediction_disposition=prediction.disposition,
            review_decision=worldtwin.ReceiptReviewDecision.RECORD_ONLY,
            created_at=_created_at(),
            created_by="worldtwin-receipt-gate",
            artifacts=(artifact,),
        )

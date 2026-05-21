from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import ix_blackfox_worldtwin as worldtwin


MODEL_ID = "deterministic-kernel-v1"


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _scenario() -> worldtwin.ScenarioManifest:
    return worldtwin.build_thermal_drift_scenario()


def _simulation() -> worldtwin.SimulationResult:
    return worldtwin.run_deterministic_simulation(
        scenario=_scenario(),
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


def _prediction() -> worldtwin.PredictionResult:
    simulation = _simulation()
    confidence = worldtwin.create_confidence_assessment(
        target_id=simulation.simulation_id,
        confidence=0.90,
        rationale="Simulation is deterministic and scenario-bounded.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
    )
    return worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=confidence,
    )


def _receipt(prediction: worldtwin.PredictionResult) -> worldtwin.PredictionReceipt:
    return worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
    )


def _chain_and_validation(
    receipt: worldtwin.PredictionReceipt,
) -> tuple[worldtwin.ReceiptChain, worldtwin.ReceiptChainValidationResult]:
    chain = worldtwin.create_receipt_chain(
        receipts=(receipt,),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
    )
    validation = worldtwin.validate_receipt_chain(
        chain=chain,
        receipts=(receipt,),
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
    )
    return chain, validation


def _policy_allow() -> worldtwin.PolicyEvaluation:
    scenario = _scenario()
    simulation = _simulation()
    assumption = worldtwin.create_assumption_record(
        name="Telemetry source is authenticated",
        category=worldtwin.AssumptionCategory.DATA_QUALITY,
        statement="The telemetry source identity is authenticated.",
        confidence=0.85,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.HIGH,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        evidence_ids=("telemetry-auth-evidence",),
        required_evidence=(worldtwin.RequiredEvidence("telemetry authentication receipt"),),
    )
    ledger = worldtwin.create_assumption_ledger(
        assumptions=(assumption,),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        scenario_id=scenario.scenario_id,
    )
    constraints = worldtwin.create_constraint_set(
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

    return worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=ledger,
        constraint_set=constraints,
        predicted_values=simulation.predicted_values(),
    )


def _reality_delta_report(
    prediction: worldtwin.PredictionResult,
    *,
    temperature: float = 87.5,
    risk_score: float = 0.55,
) -> worldtwin.RealityDeltaReport:
    observed_state = worldtwin.create_observed_state(
        dimensions=(
            worldtwin.StateDimension(
                name="temperature",
                value=temperature,
                unit="F",
                description="Observed final temperature.",
            ),
            worldtwin.StateDimension(
                name="risk_score",
                value=risk_score,
                unit="score",
                description="Observed final risk score.",
            ),
        ),
        valid_at=prediction.final_state.valid_at + timedelta(minutes=1),
        created_at=_created_at(),
        source="reality-observation-alpha",
        lineage=(prediction.final_state.state_id,),
    )

    return worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=observed_state,
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )


def _confidence_profile() -> worldtwin.ModelConfidenceProfile:
    return worldtwin.create_model_confidence_profile(
        model_id=MODEL_ID,
        base_confidence=0.90,
        observations=(),
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
    )


def _adaptation_gate_result(
    prediction: worldtwin.PredictionResult,
    receipt_validation: worldtwin.ReceiptChainValidationResult,
    policy: worldtwin.PolicyEvaluation,
    report: worldtwin.RealityDeltaReport,
    confidence_profile: worldtwin.ModelConfidenceProfile,
) -> worldtwin.AdaptationGateResult:
    candidate = worldtwin.create_adaptation_candidate(
        model_id=MODEL_ID,
        scope=worldtwin.AdaptationScope.SIMULATION_RULE,
        target_artifact_id=prediction.prediction_id,
        summary="Review deterministic thermal drift adjustment after clean evidence.",
        proposed_change_fingerprint="sha256:handoff-adaptation-alpha",
        created_at=_created_at(),
        proposed_by="worldtwin-adaptation-gate",
        evidence_ids=("evidence-adaptation-alpha",),
    )

    return worldtwin.evaluate_adaptation_gate(
        candidate=candidate,
        confidence_profile=confidence_profile,
        reality_delta_report=report,
        receipt_chain_validation=receipt_validation,
        policy_evaluation=policy,
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )


def _clean_handoff() -> worldtwin.HandoffPackage:
    prediction = _prediction()
    receipt = _receipt(prediction)
    chain, validation = _chain_and_validation(receipt)
    policy = _policy_allow()
    report = _reality_delta_report(prediction)
    confidence = _confidence_profile()
    adaptation = _adaptation_gate_result(
        prediction=prediction,
        receipt_validation=validation,
        policy=policy,
        report=report,
        confidence_profile=confidence,
    )

    return worldtwin.create_handoff_package(
        target=worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE,
        prediction=prediction,
        receipt=receipt,
        receipt_chain=chain,
        receipt_chain_validation=validation,
        policy_evaluation=policy,
        adaptation_gate_result=adaptation,
        reality_delta_report=report,
        model_confidence_profile=confidence,
        created_at=_created_at(),
        created_by="worldtwin-handoff-gate",
        requested_action="Submit evidence package to human execution-governance review.",
        notes=("human review only",),
    )


def test_handoff_package_is_ready_when_all_artifacts_are_clean() -> None:
    handoff = _clean_handoff()

    assert handoff.handoff_id.startswith("handoff-")
    assert handoff.schema_version == worldtwin.HANDOFF_SCHEMA_VERSION
    assert handoff.target is worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE
    assert handoff.decision is worldtwin.HandoffDecision.READY_FOR_REVIEW
    assert handoff.may_enter_human_review is True
    assert handoff.blocks_downstream_review is False
    assert handoff.requires_human_authority is True
    assert handoff.allowed_for_automatic_execution is False
    assert handoff.highest_reason_severity() is worldtwin.HandoffReasonSeverity.INFO
    assert "human-authority-required" in handoff.reason_codes()
    assert "receipt-chain-valid" in handoff.reason_codes()
    assert handoff.notes == ("human review only",)


def test_handoff_package_preserves_required_artifact_fingerprints() -> None:
    handoff = _clean_handoff()

    artifact_types = tuple(artifact.artifact_type for artifact in handoff.artifacts)

    assert "prediction-result" in artifact_types
    assert "prediction-receipt" in artifact_types
    assert "receipt-chain" in artifact_types
    assert "receipt-chain-validation" in artifact_types
    assert "policy-evaluation" in artifact_types
    assert "adaptation-gate-result" in artifact_types
    assert "reality-delta-report" in artifact_types
    assert "model-confidence-profile" in artifact_types
    assert handoff.artifact_table()[handoff.prediction_id]


def test_handoff_package_cautions_when_optional_review_artifacts_are_missing() -> None:
    prediction = _prediction()
    receipt = _receipt(prediction)
    chain, validation = _chain_and_validation(receipt)

    handoff = worldtwin.create_handoff_package(
        target=worldtwin.HandoffTarget.HUMAN_REVIEW_QUEUE,
        prediction=prediction,
        receipt=receipt,
        receipt_chain=chain,
        receipt_chain_validation=validation,
        created_at=_created_at(),
        created_by="worldtwin-handoff-gate",
        requested_action="Queue prediction package for human review.",
    )

    assert handoff.decision is worldtwin.HandoffDecision.CAUTION_REVIEW
    assert handoff.may_enter_human_review is True
    assert "policy-evaluation-missing" in handoff.reason_codes()
    assert "adaptation-gate-missing" in handoff.reason_codes()
    assert "reality-delta-missing" in handoff.reason_codes()
    assert "model-confidence-missing" in handoff.reason_codes()


def test_handoff_package_blocks_on_invalid_receipt_chain_validation() -> None:
    prediction = _prediction()
    receipt = _receipt(prediction)
    chain, _validation = _chain_and_validation(receipt)
    invalid_validation = worldtwin.ReceiptChainValidationResult(
        chain_id=chain.chain_id,
        status=worldtwin.ReceiptChainValidationStatus.FAIL,
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
        issues=("entry hash mismatch",),
    )

    handoff = worldtwin.create_handoff_package(
        target=worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE,
        prediction=prediction,
        receipt=receipt,
        receipt_chain=chain,
        receipt_chain_validation=invalid_validation,
        created_at=_created_at(),
        created_by="worldtwin-handoff-gate",
        requested_action="Submit evidence package to human execution-governance review.",
    )

    assert handoff.decision is worldtwin.HandoffDecision.BLOCKED
    assert handoff.blocks_downstream_review is True
    assert "receipt-chain-invalid" in handoff.reason_codes()


def test_handoff_package_quarantines_on_reality_delta_quarantine() -> None:
    prediction = _prediction()
    receipt = _receipt(prediction)
    chain, validation = _chain_and_validation(receipt)
    report = _reality_delta_report(prediction, temperature=99.0)

    handoff = worldtwin.create_handoff_package(
        target=worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE,
        prediction=prediction,
        receipt=receipt,
        receipt_chain=chain,
        receipt_chain_validation=validation,
        reality_delta_report=report,
        created_at=_created_at(),
        created_by="worldtwin-handoff-gate",
        requested_action="Submit evidence package to human execution-governance review.",
    )

    assert handoff.decision is worldtwin.HandoffDecision.QUARANTINED
    assert handoff.blocks_downstream_review is True
    assert "reality-delta-quarantine" in handoff.reason_codes()


def test_handoff_package_rejects_receipt_prediction_mismatch() -> None:
    prediction = _prediction()
    other_prediction = _prediction()
    receipt = _receipt(other_prediction)
    chain, validation = _chain_and_validation(receipt)

    with pytest.raises(ValueError, match="receipt prediction_id must match prediction prediction_id"):
        worldtwin.create_handoff_package(
            target=worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE,
            prediction=prediction,
            receipt=receipt,
            receipt_chain=chain,
            receipt_chain_validation=validation,
            created_at=_created_at(),
            created_by="worldtwin-handoff-gate",
            requested_action="Submit evidence package to human execution-governance review.",
        )


def test_handoff_package_rejects_missing_receipt_in_chain() -> None:
    prediction = _prediction()
    receipt = _receipt(prediction)
    other_receipt = _receipt(_prediction())
    chain, validation = _chain_and_validation(other_receipt)

    with pytest.raises(ValueError, match="receipt chain must contain the handoff receipt"):
        worldtwin.create_handoff_package(
            target=worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE,
            prediction=prediction,
            receipt=receipt,
            receipt_chain=chain,
            receipt_chain_validation=validation,
            created_at=_created_at(),
            created_by="worldtwin-handoff-gate",
            requested_action="Submit evidence package to human execution-governance review.",
        )


def test_handoff_package_fingerprint_is_replay_stable() -> None:
    first = _clean_handoff()
    second = _clean_handoff()

    assert first.handoff_id == second.handoff_id
    assert first.fingerprint() == second.fingerprint()


def test_handoff_package_rejects_automatic_execution_when_constructed_directly() -> None:
    reason = worldtwin.HandoffReason(
        code="human-authority-required",
        severity=worldtwin.HandoffReasonSeverity.INFO,
        message="Handoff package is review-only and requires human authority.",
        source="prediction:manual",
    )
    artifact = worldtwin.HandoffArtifact(
        artifact_id="artifact-alpha",
        artifact_type="manual",
        fingerprint="fingerprint-alpha",
        source="test",
    )

    with pytest.raises(ValueError, match="handoff package must never allow automatic execution"):
        worldtwin.HandoffPackage(
            handoff_id="handoff-manual",
            target=worldtwin.HandoffTarget.HUMAN_REVIEW_QUEUE,
            decision=worldtwin.HandoffDecision.READY_FOR_REVIEW,
            scenario_id="scenario-alpha",
            prediction_id="prediction-alpha",
            receipt_id="receipt-alpha",
            receipt_chain_id="receipt-chain-alpha",
            created_at=_created_at(),
            created_by="worldtwin-handoff-gate",
            requested_action="Manual test package.",
            reasons=(reason,),
            artifacts=(artifact,),
            allowed_for_automatic_execution=True,
        )

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import ix_blackfox_worldtwin as worldtwin


MODEL_ID = "deterministic-kernel-v1"


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


def _observed_state(
    *,
    temperature: float = 87.5,
    risk_score: float = 0.55,
) -> worldtwin.WorldState:
    prediction = _prediction()
    return worldtwin.create_observed_state(
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


def _reality_delta_report(
    *,
    temperature: float = 87.5,
    risk_score: float = 0.55,
) -> worldtwin.RealityDeltaReport:
    return worldtwin.create_reality_delta_report(
        prediction=_prediction(),
        observed_state=_observed_state(
            temperature=temperature,
            risk_score=risk_score,
        ),
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )


def _confidence_profile(base_confidence: float = 0.90) -> worldtwin.ModelConfidenceProfile:
    return worldtwin.create_model_confidence_profile(
        model_id=MODEL_ID,
        base_confidence=base_confidence,
        observations=(),
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
    )


def _receipt_chain_validation() -> worldtwin.ReceiptChainValidationResult:
    prediction = _prediction()
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        created_at=_created_at(),
        created_by="worldtwin-receipt-gate",
    )
    chain = worldtwin.create_receipt_chain(
        receipts=(receipt,),
        created_at=_created_at(),
        created_by="worldtwin-chain-gate",
    )

    return worldtwin.validate_receipt_chain(
        chain=chain,
        receipts=(receipt,),
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
    )


def _policy_allow() -> worldtwin.PolicyEvaluation:
    scenario = worldtwin.build_thermal_drift_scenario()
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


def _candidate(evidence_ids: tuple[str, ...] = ("evidence-adaptation-alpha",)) -> (
    worldtwin.AdaptationCandidate
):
    prediction = _prediction()
    return worldtwin.create_adaptation_candidate(
        model_id=MODEL_ID,
        scope=worldtwin.AdaptationScope.SIMULATION_RULE,
        target_artifact_id=prediction.prediction_id,
        summary="Adjust deterministic thermal drift rule after clean reality-delta evidence.",
        proposed_change_fingerprint="sha256:adaptation-change-alpha",
        created_at=_created_at(),
        proposed_by="worldtwin-adaptation-gate",
        evidence_ids=evidence_ids,
        tags=("thermal", "review-only"),
    )


def test_adaptation_candidate_is_human_authority_only() -> None:
    candidate = _candidate()

    assert candidate.candidate_id.startswith("adaptation-candidate-")
    assert candidate.schema_version == worldtwin.ADAPTATION_SCHEMA_VERSION
    assert candidate.model_id == MODEL_ID
    assert candidate.scope is worldtwin.AdaptationScope.SIMULATION_RULE
    assert candidate.requires_human_authority is True
    assert candidate.evidence_ids == ("evidence-adaptation-alpha",)
    assert candidate.tags == ("review-only", "thermal")


def test_adaptation_gate_ready_for_human_review_when_all_evidence_is_clean() -> None:
    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        reality_delta_report=_reality_delta_report(),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.gate_result_id.startswith("adaptation-gate-result-")
    assert result.schema_version == worldtwin.ADAPTATION_SCHEMA_VERSION
    assert result.decision is worldtwin.AdaptationDecision.READY_FOR_HUMAN_REVIEW
    assert result.may_enter_human_review is True
    assert result.blocks_adaptation_review is False
    assert result.requires_human_authority is True
    assert result.allowed_for_automatic_application is False
    assert result.highest_reason_severity() is worldtwin.AdaptationReasonSeverity.INFO
    assert result.reason_codes() == (
        "human-authority-required",
        "model-trusted",
        "policy-allow",
        "reality-delta-match",
        "receipt-chain-valid",
    )


def test_adaptation_gate_cautions_when_candidate_evidence_is_missing() -> None:
    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(evidence_ids=()),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        reality_delta_report=_reality_delta_report(),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.decision is worldtwin.AdaptationDecision.CAUTION_REVIEW
    assert result.may_enter_human_review is True
    assert "candidate-missing-evidence" in result.reason_codes()


def test_adaptation_gate_denies_watchlist_model() -> None:
    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.50),
        reality_delta_report=_reality_delta_report(),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.decision is worldtwin.AdaptationDecision.DENY
    assert result.blocks_adaptation_review is True
    assert "model-watchlist" in result.reason_codes()


def test_adaptation_gate_quarantines_suspended_model() -> None:
    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.05),
        reality_delta_report=_reality_delta_report(),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.decision is worldtwin.AdaptationDecision.QUARANTINE
    assert result.blocks_adaptation_review is True
    assert "model-confidence-blocks-adaptation" in result.reason_codes()


def test_adaptation_gate_denies_breached_reality_delta() -> None:
    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        reality_delta_report=_reality_delta_report(temperature=92.0),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.decision is worldtwin.AdaptationDecision.DENY
    assert "reality-delta-breach" in result.reason_codes()


def test_adaptation_gate_quarantines_reality_delta_quarantine() -> None:
    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        reality_delta_report=_reality_delta_report(temperature=99.0),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.decision is worldtwin.AdaptationDecision.QUARANTINE
    assert "reality-delta-quarantine" in result.reason_codes()


def test_adaptation_gate_denies_invalid_receipt_chain() -> None:
    invalid_validation = worldtwin.ReceiptChainValidationResult(
        chain_id="receipt-chain-alpha",
        status=worldtwin.ReceiptChainValidationStatus.FAIL,
        checked_at=_created_at(),
        checked_by="worldtwin-chain-gate",
        issues=("entry hash mismatch",),
    )

    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        reality_delta_report=_reality_delta_report(),
        receipt_chain_validation=invalid_validation,
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.decision is worldtwin.AdaptationDecision.DENY
    assert "receipt-chain-invalid" in result.reason_codes()


def test_adaptation_gate_cautions_when_optional_review_artifacts_are_missing() -> None:
    result = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert result.decision is worldtwin.AdaptationDecision.CAUTION_REVIEW
    assert "reality-delta-missing" in result.reason_codes()
    assert "receipt-chain-validation-missing" in result.reason_codes()
    assert "policy-evaluation-missing" in result.reason_codes()


def test_adaptation_gate_rejects_model_id_mismatch() -> None:
    other_profile = worldtwin.create_model_confidence_profile(
        model_id="other-model",
        base_confidence=0.90,
        observations=(),
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
    )

    with pytest.raises(ValueError, match="candidate model_id must match confidence profile model_id"):
        worldtwin.evaluate_adaptation_gate(
            candidate=_candidate(),
            confidence_profile=other_profile,
            created_at=_created_at(),
            evaluated_by="worldtwin-adaptation-gate",
        )


def test_adaptation_candidate_rejects_non_human_authority_mode() -> None:
    with pytest.raises(ValueError, match="adaptation candidate must require human authority"):
        worldtwin.AdaptationCandidate(
            candidate_id="adaptation-candidate-manual",
            model_id=MODEL_ID,
            scope=worldtwin.AdaptationScope.SIMULATION_RULE,
            target_artifact_id="prediction-alpha",
            summary="Unsafe direct adaptation candidate.",
            proposed_change_fingerprint="sha256:manual",
            created_at=_created_at(),
            proposed_by="worldtwin-adaptation-gate",
            requires_human_authority=False,
        )


def test_adaptation_gate_result_rejects_automatic_application() -> None:
    reason = worldtwin.AdaptationGateReason(
        code="human-authority-required",
        severity=worldtwin.AdaptationReasonSeverity.INFO,
        message="Adaptation candidate is review-only and requires human authority.",
        source="candidate:manual",
    )

    with pytest.raises(ValueError, match="adaptation gate must never allow automatic application"):
        worldtwin.AdaptationGateResult(
            gate_result_id="adaptation-gate-result-manual",
            candidate_id="adaptation-candidate-manual",
            model_id=MODEL_ID,
            decision=worldtwin.AdaptationDecision.READY_FOR_HUMAN_REVIEW,
            created_at=_created_at(),
            evaluated_by="worldtwin-adaptation-gate",
            reasons=(reason,),
            confidence_profile_id="model-confidence-profile-manual",
            allowed_for_automatic_application=True,
        )


def test_adaptation_gate_fingerprint_is_replay_stable() -> None:
    first = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        reality_delta_report=_reality_delta_report(),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )
    second = worldtwin.evaluate_adaptation_gate(
        candidate=_candidate(),
        confidence_profile=_confidence_profile(base_confidence=0.90),
        reality_delta_report=_reality_delta_report(),
        receipt_chain_validation=_receipt_chain_validation(),
        policy_evaluation=_policy_allow(),
        created_at=_created_at(),
        evaluated_by="worldtwin-adaptation-gate",
    )

    assert first.gate_result_id == second.gate_result_id
    assert first.fingerprint() == second.fingerprint()

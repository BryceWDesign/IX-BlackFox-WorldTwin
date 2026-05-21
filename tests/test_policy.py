from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _assumption_ledger() -> worldtwin.AssumptionLedger:
    assumption = worldtwin.create_assumption_record(
        name="Telemetry source is authenticated",
        category=worldtwin.AssumptionCategory.DATA_QUALITY,
        statement="The telemetry source identity is authenticated.",
        confidence=0.80,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.HIGH,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        evidence_ids=("telemetry-auth-evidence",),
        required_evidence=(worldtwin.RequiredEvidence("telemetry authentication receipt"),),
    )
    return worldtwin.create_assumption_ledger(
        assumptions=(assumption,),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        scenario_id=worldtwin.build_thermal_drift_scenario().scenario_id,
    )


def _constraint_set() -> worldtwin.ConstraintSet:
    return worldtwin.create_constraint_set(
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
        scenario_id=worldtwin.build_thermal_drift_scenario().scenario_id,
    )


def test_policy_allows_clean_valid_scenario_with_passing_constraints() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    evaluation = worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=_assumption_ledger(),
        constraint_set=_constraint_set(),
        predicted_values={"temperature": 120.0, "risk_score": 0.20},
    )

    assert evaluation.policy_evaluation_id.startswith("policy-evaluation-")
    assert evaluation.schema_version == worldtwin.POLICY_SCHEMA_VERSION
    assert evaluation.decision is worldtwin.PolicyDecision.ALLOW
    assert evaluation.allows_execution_review is True
    assert evaluation.blocks_execution_review is False
    assert evaluation.reason_codes() == ("policy-clean",)
    assert evaluation.highest_reason_severity() is worldtwin.PolicyReasonSeverity.INFO


def test_policy_returns_caution_when_optional_evidence_gates_are_missing() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    evaluation = worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
    )

    assert evaluation.decision is worldtwin.PolicyDecision.CAUTION
    assert evaluation.requires_human_caution is True
    assert "missing-assumption-ledger" in evaluation.reason_codes()
    assert "missing-constraint-set" in evaluation.reason_codes()


def test_policy_denies_invalid_scenario_or_hard_constraint_failure() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    evaluation = worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=_assumption_ledger(),
        constraint_set=_constraint_set(),
        predicted_values={"temperature": 220.0, "risk_score": 0.20},
    )

    assert evaluation.decision is worldtwin.PolicyDecision.DENY
    assert evaluation.blocks_execution_review is True
    assert "constraint-hard-failed" in evaluation.reason_codes()


def test_policy_returns_caution_for_soft_constraint_failure() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    evaluation = worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=_assumption_ledger(),
        constraint_set=_constraint_set(),
        predicted_values={"temperature": 120.0, "risk_score": 0.95},
    )

    assert evaluation.decision is worldtwin.PolicyDecision.CAUTION
    assert evaluation.requires_human_caution is True
    assert "constraint-soft-failed" in evaluation.reason_codes()


def test_policy_quarantines_disputed_assumptions() -> None:
    assumption = worldtwin.create_assumption_record(
        name="Policy snapshot remains valid",
        category=worldtwin.AssumptionCategory.POLICY,
        statement="The policy snapshot still applies.",
        confidence=0.70,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.CRITICAL,
        status=worldtwin.AssumptionStatus.DISPUTED,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        evidence_ids=("policy-evidence",),
    )
    ledger = worldtwin.create_assumption_ledger(
        assumptions=(assumption,),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
    )

    evaluation = worldtwin.evaluate_worldtwin_policy(
        scenario=worldtwin.build_thermal_drift_scenario(),
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=ledger,
        constraint_set=_constraint_set(),
        predicted_values={"temperature": 120.0, "risk_score": 0.20},
    )

    assert evaluation.decision is worldtwin.PolicyDecision.QUARANTINE
    assert evaluation.blocks_execution_review is True
    assert "assumption-disputed" in evaluation.reason_codes()


def test_policy_quarantines_stale_assumptions() -> None:
    assumption = worldtwin.create_assumption_record(
        name="Scenario boundary remains stable",
        category=worldtwin.AssumptionCategory.SCENARIO_BOUNDARY,
        statement="The scenario boundary remains stable during review.",
        confidence=0.80,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.HIGH,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        evidence_ids=("boundary-evidence",),
        expires_at=_created_at() + timedelta(minutes=1),
    )
    ledger = worldtwin.create_assumption_ledger(
        assumptions=(assumption,),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
    )

    evaluation = worldtwin.evaluate_worldtwin_policy(
        scenario=worldtwin.build_thermal_drift_scenario(),
        created_at=_created_at() + timedelta(minutes=2),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=ledger,
        constraint_set=_constraint_set(),
        predicted_values={"temperature": 120.0, "risk_score": 0.20},
    )

    assert evaluation.decision is worldtwin.PolicyDecision.QUARANTINE
    assert "assumption-stale" in evaluation.reason_codes()


def test_policy_evaluation_fingerprint_is_deterministic() -> None:
    scenario = worldtwin.build_thermal_drift_scenario()
    first = worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=_assumption_ledger(),
        constraint_set=_constraint_set(),
        predicted_values={"temperature": 120.0, "risk_score": 0.20},
    )
    second = worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        created_at=_created_at(),
        evaluator="worldtwin-policy-gate",
        assumption_ledger=_assumption_ledger(),
        constraint_set=_constraint_set(),
        predicted_values={"risk_score": 0.20, "temperature": 120.0},
    )

    assert first.policy_evaluation_id == second.policy_evaluation_id
    assert first.fingerprint() == second.fingerprint()


def test_policy_evaluation_rejects_empty_reason_list_when_constructed_directly() -> None:
    with pytest.raises(ValueError, match="policy evaluation requires at least one reason"):
        worldtwin.PolicyEvaluation(
            policy_evaluation_id="policy-evaluation-manual",
            decision=worldtwin.PolicyDecision.ALLOW,
            scenario_id="scenario-alpha",
            created_at=_created_at(),
            evaluator="worldtwin-policy-gate",
            reasons=(),
        )

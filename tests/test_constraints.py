from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _temperature_rule() -> worldtwin.ConstraintRule:
    return worldtwin.create_constraint_rule(
        name="Temperature review limit",
        target="temperature",
        operator=worldtwin.ConstraintOperator.LESS_THAN_OR_EQUAL,
        severity=worldtwin.ConstraintSeverity.CRITICAL,
        description="Predicted temperature must stay under the human-review limit.",
        limit_value=180.0,
        is_hard=True,
        evidence_ids=("policy-evidence-temperature",),
        tags=("thermal", "safety"),
    )


def _risk_rule() -> worldtwin.ConstraintRule:
    return worldtwin.create_constraint_rule(
        name="Risk caution band",
        target="risk_score",
        operator=worldtwin.ConstraintOperator.LESS_THAN_OR_EQUAL,
        severity=worldtwin.ConstraintSeverity.WARNING,
        description="Risk score above this value should trigger caution.",
        limit_value=0.70,
        is_hard=False,
        evidence_ids=("policy-evidence-risk",),
        tags=("risk", "review"),
    )


def test_constraint_rule_evaluates_scalar_limit_pass_and_fail() -> None:
    rule = _temperature_rule()

    passing = rule.evaluate(120.0)
    failing = rule.evaluate(220.0)

    assert rule.rule_id.startswith("constraint-rule-")
    assert rule.schema_version == worldtwin.CONSTRAINT_SCHEMA_VERSION
    assert passing.passed is True
    assert passing.failed is False
    assert passing.severity is worldtwin.ConstraintSeverity.CRITICAL
    assert "passed" in passing.message
    assert failing.passed is False
    assert failing.failed is True
    assert "failed" in failing.message


def test_constraint_rule_evaluates_missing_target_as_failure() -> None:
    rule = _temperature_rule()
    evaluation = rule.evaluate(None)

    assert evaluation.passed is False
    assert evaluation.observed_value is None
    assert evaluation.message == "Constraint target 'temperature' is missing."


def test_range_constraint_evaluates_between_inclusive() -> None:
    rule = worldtwin.create_constraint_rule(
        name="Load operating band",
        target="load",
        operator=worldtwin.ConstraintOperator.BETWEEN_INCLUSIVE,
        severity=worldtwin.ConstraintSeverity.ERROR,
        description="Load must remain inside the operating band.",
        lower_bound=0.10,
        upper_bound=0.90,
    )

    assert rule.evaluate(0.10).passed is True
    assert rule.evaluate(0.50).passed is True
    assert rule.evaluate(0.90).passed is True
    assert rule.evaluate(0.91).passed is False


def test_range_constraint_rejects_missing_or_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="range constraint requires lower_bound and upper_bound"):
        worldtwin.create_constraint_rule(
            name="Bad range",
            target="load",
            operator=worldtwin.ConstraintOperator.BETWEEN_INCLUSIVE,
            severity=worldtwin.ConstraintSeverity.ERROR,
            description="This range is missing an upper bound.",
            lower_bound=0.0,
        )

    with pytest.raises(
        ValueError,
        match="constraint lower_bound must be less than or equal to upper_bound",
    ):
        worldtwin.create_constraint_rule(
            name="Inverted range",
            target="load",
            operator=worldtwin.ConstraintOperator.BETWEEN_INCLUSIVE,
            severity=worldtwin.ConstraintSeverity.ERROR,
            description="This range has inverted bounds.",
            lower_bound=1.0,
            upper_bound=0.0,
        )


def test_scalar_constraint_rejects_missing_limit() -> None:
    with pytest.raises(ValueError, match="scalar constraint requires limit_value"):
        worldtwin.create_constraint_rule(
            name="Missing scalar limit",
            target="temperature",
            operator=worldtwin.ConstraintOperator.LESS_THAN_OR_EQUAL,
            severity=worldtwin.ConstraintSeverity.ERROR,
            description="This scalar constraint is missing a limit value.",
        )


def test_constraint_set_evaluates_pass_caution_and_fail_decisions() -> None:
    constraint_set = worldtwin.create_constraint_set(
        rules=(_temperature_rule(), _risk_rule()),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        scenario_id="scenario-alpha",
        notes=("evaluate predicted state before handoff",),
    )

    assert constraint_set.constraint_set_id.startswith("constraint-set-")
    assert constraint_set.schema_version == worldtwin.CONSTRAINT_SCHEMA_VERSION
    assert constraint_set.scenario_id == "scenario-alpha"
    assert constraint_set.decision({"temperature": 120.0, "risk_score": 0.40}) is (
        worldtwin.ConstraintDecision.PASS
    )
    assert constraint_set.decision({"temperature": 120.0, "risk_score": 0.90}) is (
        worldtwin.ConstraintDecision.CAUTION
    )
    assert constraint_set.decision({"temperature": 220.0, "risk_score": 0.40}) is (
        worldtwin.ConstraintDecision.FAIL
    )


def test_constraint_set_reports_failed_evaluations_and_highest_severity() -> None:
    constraint_set = worldtwin.create_constraint_set(
        rules=(_temperature_rule(), _risk_rule()),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
    )
    evaluations = constraint_set.evaluate({"temperature": 220.0, "risk_score": 0.90})

    assert evaluations.passed is False
    assert tuple(evaluation.rule_id for evaluation in evaluations.failed_evaluations()) == (
        _risk_rule().rule_id,
        _temperature_rule().rule_id,
    )
    assert evaluations.highest_failed_severity() is worldtwin.ConstraintSeverity.CRITICAL
    assert constraint_set.hard_failed_rule_ids({"temperature": 220.0, "risk_score": 0.90}) == (
        _temperature_rule().rule_id,
    )


def test_constraint_set_fingerprint_is_deterministic_for_reordered_inputs() -> None:
    first = worldtwin.create_constraint_set(
        rules=(_risk_rule(), _temperature_rule()),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        notes=("b", "a"),
    )
    second = worldtwin.create_constraint_set(
        rules=(_temperature_rule(), _risk_rule()),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        notes=("a", "b"),
    )

    assert first.constraint_set_id == second.constraint_set_id
    assert first.fingerprint() == second.fingerprint()


def test_constraint_set_rejects_empty_or_duplicate_rules() -> None:
    with pytest.raises(ValueError, match="constraint set requires at least one rule"):
        worldtwin.create_constraint_set(
            rules=(),
            created_at=_created_at(),
            owner="worldtwin-test-suite",
        )

    rule = _temperature_rule()
    with pytest.raises(ValueError, match=f"duplicate constraint rule id: {rule.rule_id}"):
        worldtwin.create_constraint_set(
            rules=(rule, rule),
            created_at=_created_at(),
            owner="worldtwin-test-suite",
        )


def test_constraint_set_normalizes_timezone_to_utc() -> None:
    local_time = datetime(2026, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=-8)))
    constraint_set = worldtwin.create_constraint_set(
        rules=(_temperature_rule(),),
        created_at=local_time,
        owner="worldtwin-test-suite",
    )

    assert constraint_set.created_at == _created_at()


def test_constraint_set_rejects_naive_created_at() -> None:
    with pytest.raises(ValueError, match="constraint set created_at must be timezone-aware"):
        worldtwin.create_constraint_set(
            rules=(_temperature_rule(),),
            created_at=datetime(2026, 1, 1, 12, 0),
            owner="worldtwin-test-suite",
        )

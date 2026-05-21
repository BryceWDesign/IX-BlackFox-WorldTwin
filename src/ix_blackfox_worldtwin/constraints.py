"""Constraint engine for IX-BlackFox-WorldTwin.

Constraints turn scenario boundaries into executable checks. They do not grant
permission to act. They produce reviewable pass/fail evidence that later
simulation, prediction, receipt, policy, and handoff modules can inspect before
anything moves toward human-authorized execution review.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

CONSTRAINT_SCHEMA_VERSION = "constraint-engine-v1"
CONSTRAINT_ID_DIGEST_LENGTH = 16


class ConstraintOperator(StrEnum):
    """Supported scalar constraint operators."""

    LESS_THAN = "less-than"
    LESS_THAN_OR_EQUAL = "less-than-or-equal"
    GREATER_THAN = "greater-than"
    GREATER_THAN_OR_EQUAL = "greater-than-or-equal"
    EQUAL = "equal"
    BETWEEN_INCLUSIVE = "between-inclusive"
    OUTSIDE_INCLUSIVE = "outside-inclusive"


class ConstraintSeverity(StrEnum):
    """Severity applied when a constraint fails."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ConstraintDecision(StrEnum):
    """Aggregate decision after evaluating a constraint set."""

    PASS = "pass"
    CAUTION = "caution"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ConstraintEvaluation:
    """Result of evaluating one constraint rule against one value."""

    rule_id: str
    target: str
    observed_value: float | None
    passed: bool
    severity: ConstraintSeverity
    message: str

    def __post_init__(self) -> None:
        """Validate and normalize a constraint evaluation."""

        object.__setattr__(self, "rule_id", _require_non_empty(self.rule_id, "rule id"))
        object.__setattr__(self, "target", _require_non_empty(self.target, "constraint target"))
        if self.observed_value is not None:
            object.__setattr__(
                self,
                "observed_value",
                _require_finite_float(self.observed_value, "observed value"),
            )
        object.__setattr__(self, "message", _require_non_empty(self.message, "message"))

    @property
    def failed(self) -> bool:
        """Return True when this evaluation failed."""

        return not self.passed

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "message": self.message,
            "observed_value": self.observed_value,
            "passed": self.passed,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class ConstraintRule:
    """A scalar rule used to check bounded scenario or prediction values."""

    rule_id: str
    name: str
    target: str
    operator: ConstraintOperator
    severity: ConstraintSeverity
    description: str
    limit_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    is_hard: bool = True
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    schema_version: str = CONSTRAINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a constraint rule."""

        limit_value = _normalize_optional_float(self.limit_value, "constraint limit value")
        lower_bound = _normalize_optional_float(self.lower_bound, "constraint lower bound")
        upper_bound = _normalize_optional_float(self.upper_bound, "constraint upper bound")

        if self.operator in {
            ConstraintOperator.BETWEEN_INCLUSIVE,
            ConstraintOperator.OUTSIDE_INCLUSIVE,
        }:
            if lower_bound is None or upper_bound is None:
                raise ValueError("range constraint requires lower_bound and upper_bound")
            if lower_bound > upper_bound:
                raise ValueError("constraint lower_bound must be less than or equal to upper_bound")
        elif limit_value is None:
            raise ValueError("scalar constraint requires limit_value")

        object.__setattr__(self, "rule_id", _require_non_empty(self.rule_id, "rule id"))
        object.__setattr__(self, "name", _require_non_empty(self.name, "constraint name"))
        object.__setattr__(self, "target", _require_non_empty(self.target, "constraint target"))
        object.__setattr__(
            self,
            "description",
            _require_non_empty(self.description, "constraint description"),
        )
        object.__setattr__(self, "limit_value", limit_value)
        object.__setattr__(self, "lower_bound", lower_bound)
        object.__setattr__(self, "upper_bound", upper_bound)
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_unique_text_tuple(self.evidence_ids, "evidence id"),
        )
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "constraint tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "constraint schema version"),
        )

    def evaluate(self, observed_value: float | None) -> ConstraintEvaluation:
        """Evaluate this rule against an observed value."""

        if observed_value is None:
            return ConstraintEvaluation(
                rule_id=self.rule_id,
                target=self.target,
                observed_value=None,
                passed=False,
                severity=self.severity,
                message=f"Constraint target '{self.target}' is missing.",
            )

        value = _require_finite_float(observed_value, "observed value")
        passed = _evaluate_operator(
            value=value,
            operator=self.operator,
            limit_value=self.limit_value,
            lower_bound=self.lower_bound,
            upper_bound=self.upper_bound,
        )
        message = (
            f"Constraint '{self.name}' passed for target '{self.target}'."
            if passed
            else f"Constraint '{self.name}' failed for target '{self.target}'."
        )

        return ConstraintEvaluation(
            rule_id=self.rule_id,
            target=self.target,
            observed_value=value,
            passed=passed,
            severity=self.severity,
            message=message,
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return _canonical_constraint_payload(
            rule_id=self.rule_id,
            name=self.name,
            target=self.target,
            operator=self.operator,
            severity=self.severity,
            description=self.description,
            limit_value=self.limit_value,
            lower_bound=self.lower_bound,
            upper_bound=self.upper_bound,
            is_hard=self.is_hard,
            evidence_ids=self.evidence_ids,
            tags=self.tags,
            schema_version=self.schema_version,
        )

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this constraint rule."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ConstraintEvaluationSet:
    """Aggregate result from evaluating a constraint set."""

    constraint_set_id: str
    evaluations: tuple[ConstraintEvaluation, ...]

    def __post_init__(self) -> None:
        """Validate and normalize a constraint evaluation set."""

        object.__setattr__(
            self,
            "constraint_set_id",
            _require_non_empty(self.constraint_set_id, "constraint set id"),
        )
        object.__setattr__(
            self,
            "evaluations",
            tuple(sorted(self.evaluations, key=lambda evaluation: evaluation.rule_id)),
        )

    @property
    def passed(self) -> bool:
        """Return True when all constraint evaluations passed."""

        return all(evaluation.passed for evaluation in self.evaluations)

    def failed_evaluations(self) -> tuple[ConstraintEvaluation, ...]:
        """Return failed evaluations in deterministic order."""

        return tuple(evaluation for evaluation in self.evaluations if evaluation.failed)

    def highest_failed_severity(self) -> ConstraintSeverity | None:
        """Return the highest severity among failed evaluations, or None."""

        failed = self.failed_evaluations()
        if not failed:
            return None

        return max((evaluation.severity for evaluation in failed), key=_severity_rank)

    def decision(self, hard_failed_rule_ids: tuple[str, ...]) -> ConstraintDecision:
        """Return an aggregate decision using failed hard-rule ids."""

        failed = self.failed_evaluations()
        if not failed:
            return ConstraintDecision.PASS
        if hard_failed_rule_ids:
            return ConstraintDecision.FAIL
        return ConstraintDecision.CAUTION

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "constraint_set_id": self.constraint_set_id,
            "evaluations": [evaluation.canonical_payload() for evaluation in self.evaluations],
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this evaluation set."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ConstraintSet:
    """A deterministic collection of constraint rules."""

    constraint_set_id: str
    rules: tuple[ConstraintRule, ...]
    created_at: datetime
    owner: str
    scenario_id: str = ""
    notes: tuple[str, ...] = ()
    schema_version: str = CONSTRAINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a constraint set."""

        object.__setattr__(
            self,
            "constraint_set_id",
            _require_non_empty(self.constraint_set_id, "constraint set id"),
        )
        object.__setattr__(self, "rules", _normalize_constraint_rules(self.rules))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "constraint set created_at"),
        )
        object.__setattr__(self, "owner", _require_non_empty(self.owner, "constraint set owner"))
        object.__setattr__(self, "scenario_id", self.scenario_id.strip())
        object.__setattr__(
            self, "notes", _normalize_unique_text_tuple(self.notes, "constraint note")
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "constraint schema version"),
        )

    def evaluate(self, values: Mapping[str, float]) -> ConstraintEvaluationSet:
        """Evaluate every rule against a mapping of target values."""

        evaluations = tuple(rule.evaluate(values.get(rule.target)) for rule in self.rules)
        return ConstraintEvaluationSet(
            constraint_set_id=self.constraint_set_id,
            evaluations=evaluations,
        )

    def hard_rule_ids(self) -> tuple[str, ...]:
        """Return ids for hard rules."""

        return tuple(rule.rule_id for rule in self.rules if rule.is_hard)

    def soft_rule_ids(self) -> tuple[str, ...]:
        """Return ids for soft rules."""

        return tuple(rule.rule_id for rule in self.rules if not rule.is_hard)

    def hard_failed_rule_ids(self, values: Mapping[str, float]) -> tuple[str, ...]:
        """Return hard rule ids that fail against supplied values."""

        evaluations = self.evaluate(values)
        hard_rule_ids = set(self.hard_rule_ids())
        return tuple(
            evaluation.rule_id
            for evaluation in evaluations.failed_evaluations()
            if evaluation.rule_id in hard_rule_ids
        )

    def decision(self, values: Mapping[str, float]) -> ConstraintDecision:
        """Return pass/caution/fail for supplied target values."""

        evaluations = self.evaluate(values)
        return evaluations.decision(self.hard_failed_rule_ids(values))

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "constraint_set_id": self.constraint_set_id,
            "created_at": self.created_at.isoformat(),
            "notes": list(self.notes),
            "owner": self.owner,
            "rules": [rule.canonical_payload() for rule in self.rules],
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this constraint set."""

        return _stable_sha256(self.canonical_payload())


def create_constraint_rule(
    *,
    name: str,
    target: str,
    operator: ConstraintOperator,
    severity: ConstraintSeverity,
    description: str,
    limit_value: float | None = None,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
    is_hard: bool = True,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    rule_id: str | None = None,
) -> ConstraintRule:
    """Create a validated constraint rule with a deterministic id by default."""

    normalized_name = _require_non_empty(name, "constraint name")
    normalized_target = _require_non_empty(target, "constraint target")
    normalized_description = _require_non_empty(description, "constraint description")
    normalized_limit = _normalize_optional_float(limit_value, "constraint limit value")
    normalized_lower = _normalize_optional_float(lower_bound, "constraint lower bound")
    normalized_upper = _normalize_optional_float(upper_bound, "constraint upper bound")
    normalized_evidence_ids = _normalize_unique_text_tuple(evidence_ids, "evidence id")
    normalized_tags = _normalize_unique_text_tuple(tags, "constraint tag")
    resolved_rule_id = rule_id or make_constraint_rule_id(
        name=normalized_name,
        target=normalized_target,
        operator=operator,
        severity=severity,
        description=normalized_description,
        limit_value=normalized_limit,
        lower_bound=normalized_lower,
        upper_bound=normalized_upper,
        is_hard=is_hard,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
    )

    return ConstraintRule(
        rule_id=resolved_rule_id,
        name=normalized_name,
        target=normalized_target,
        operator=operator,
        severity=severity,
        description=normalized_description,
        limit_value=normalized_limit,
        lower_bound=normalized_lower,
        upper_bound=normalized_upper,
        is_hard=is_hard,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
    )


def create_constraint_set(
    *,
    rules: tuple[ConstraintRule, ...],
    created_at: datetime,
    owner: str,
    scenario_id: str = "",
    notes: tuple[str, ...] = (),
    constraint_set_id: str | None = None,
) -> ConstraintSet:
    """Create a validated constraint set with a deterministic id by default."""

    normalized_rules = _normalize_constraint_rules(rules)
    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "constraint set created_at",
    )
    normalized_owner = _require_non_empty(owner, "constraint set owner")
    normalized_notes = _normalize_unique_text_tuple(notes, "constraint note")
    normalized_scenario_id = scenario_id.strip()
    resolved_constraint_set_id = constraint_set_id or make_constraint_set_id(
        rules=normalized_rules,
        created_at=normalized_created_at,
        owner=normalized_owner,
        scenario_id=normalized_scenario_id,
        notes=normalized_notes,
    )

    return ConstraintSet(
        constraint_set_id=resolved_constraint_set_id,
        rules=normalized_rules,
        created_at=normalized_created_at,
        owner=normalized_owner,
        scenario_id=normalized_scenario_id,
        notes=normalized_notes,
    )


def make_constraint_rule_id(
    *,
    name: str,
    target: str,
    operator: ConstraintOperator,
    severity: ConstraintSeverity,
    description: str,
    limit_value: float | None = None,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
    is_hard: bool = True,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> str:
    """Create a deterministic constraint rule id."""

    payload = _canonical_constraint_payload(
        rule_id="",
        name=_require_non_empty(name, "constraint name"),
        target=_require_non_empty(target, "constraint target"),
        operator=operator,
        severity=severity,
        description=_require_non_empty(description, "constraint description"),
        limit_value=_normalize_optional_float(limit_value, "constraint limit value"),
        lower_bound=_normalize_optional_float(lower_bound, "constraint lower bound"),
        upper_bound=_normalize_optional_float(upper_bound, "constraint upper bound"),
        is_hard=is_hard,
        evidence_ids=_normalize_unique_text_tuple(evidence_ids, "evidence id"),
        tags=_normalize_unique_text_tuple(tags, "constraint tag"),
        schema_version=CONSTRAINT_SCHEMA_VERSION,
    )
    digest = _stable_sha256(payload)[:CONSTRAINT_ID_DIGEST_LENGTH]
    return f"constraint-rule-{digest}"


def make_constraint_set_id(
    *,
    rules: tuple[ConstraintRule, ...],
    created_at: datetime,
    owner: str,
    scenario_id: str = "",
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic constraint set id."""

    payload = {
        "created_at": _require_aware_utc_datetime(
            created_at,
            "constraint set created_at",
        ).isoformat(),
        "notes": list(_normalize_unique_text_tuple(notes, "constraint note")),
        "owner": _require_non_empty(owner, "constraint set owner"),
        "rules": [rule.canonical_payload() for rule in _normalize_constraint_rules(rules)],
        "scenario_id": scenario_id.strip(),
        "schema_version": CONSTRAINT_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:CONSTRAINT_ID_DIGEST_LENGTH]
    return f"constraint-set-{digest}"


def _evaluate_operator(
    *,
    value: float,
    operator: ConstraintOperator,
    limit_value: float | None,
    lower_bound: float | None,
    upper_bound: float | None,
) -> bool:
    if operator is ConstraintOperator.LESS_THAN:
        return limit_value is not None and value < limit_value
    if operator is ConstraintOperator.LESS_THAN_OR_EQUAL:
        return limit_value is not None and value <= limit_value
    if operator is ConstraintOperator.GREATER_THAN:
        return limit_value is not None and value > limit_value
    if operator is ConstraintOperator.GREATER_THAN_OR_EQUAL:
        return limit_value is not None and value >= limit_value
    if operator is ConstraintOperator.EQUAL:
        return limit_value is not None and math.isclose(value, limit_value)
    if operator is ConstraintOperator.BETWEEN_INCLUSIVE:
        return (
            lower_bound is not None
            and upper_bound is not None
            and lower_bound <= value <= upper_bound
        )
    if operator is ConstraintOperator.OUTSIDE_INCLUSIVE:
        return (
            lower_bound is not None
            and upper_bound is not None
            and (value <= lower_bound or value >= upper_bound)
        )
    raise ValueError(f"unsupported constraint operator: {operator}")


def _canonical_constraint_payload(
    *,
    rule_id: str,
    name: str,
    target: str,
    operator: ConstraintOperator,
    severity: ConstraintSeverity,
    description: str,
    limit_value: float | None,
    lower_bound: float | None,
    upper_bound: float | None,
    is_hard: bool,
    evidence_ids: tuple[str, ...],
    tags: tuple[str, ...],
    schema_version: str,
) -> dict[str, Any]:
    return {
        "description": description,
        "evidence_ids": list(evidence_ids),
        "is_hard": is_hard,
        "limit_value": limit_value,
        "lower_bound": lower_bound,
        "name": name,
        "operator": operator.value,
        "rule_id": rule_id,
        "schema_version": schema_version,
        "severity": severity.value,
        "tags": list(tags),
        "target": target,
        "upper_bound": upper_bound,
    }


def _normalize_constraint_rules(rules: tuple[ConstraintRule, ...]) -> tuple[ConstraintRule, ...]:
    if not rules:
        raise ValueError("constraint set requires at least one rule")

    seen_rule_ids: set[str] = set()
    normalized_rules: list[ConstraintRule] = []

    for rule in rules:
        if rule.rule_id in seen_rule_ids:
            raise ValueError(f"duplicate constraint rule id: {rule.rule_id}")
        seen_rule_ids.add(rule.rule_id)
        normalized_rules.append(rule)

    return tuple(sorted(normalized_rules, key=lambda item: item.rule_id))


def _severity_rank(severity: ConstraintSeverity) -> int:
    ranks = {
        ConstraintSeverity.INFO: 0,
        ConstraintSeverity.WARNING: 1,
        ConstraintSeverity.ERROR: 2,
        ConstraintSeverity.CRITICAL: 3,
    }
    return ranks[severity]


def _normalize_optional_float(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    return _require_finite_float(value, field_name)


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized_values = _normalize_text_tuple(values, field_name)
    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError(f"duplicate {field_name}")
    return tuple(sorted(normalized_values))


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        normalized_values.append(_require_non_empty(value, field_name))
    return tuple(normalized_values)


def _require_non_empty(value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")
    return normalized_value


def _require_finite_float(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return float(value)


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()

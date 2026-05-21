"""Policy evaluation for IX-BlackFox-WorldTwin.

The policy gate combines scenario validation, assumption-ledger health, and
constraint outcomes into a reviewable decision. It does not authorize execution.
It produces a bounded recommendation that later receipt, handoff, and
BlackFox-facing packages can preserve for human review.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.assumptions import AssumptionLedger
from ix_blackfox_worldtwin.constraints import ConstraintDecision, ConstraintSet
from ix_blackfox_worldtwin.scenario import ScenarioManifest
from ix_blackfox_worldtwin.scenario_validation import (
    ScenarioValidationSeverity,
    validate_scenario_manifest,
)

POLICY_SCHEMA_VERSION = "worldtwin-policy-v1"
POLICY_ID_DIGEST_LENGTH = 16


class PolicyDecision(StrEnum):
    """Policy decision levels for WorldTwin evidence review."""

    ALLOW = "allow"
    CAUTION = "caution"
    DENY = "deny"
    QUARANTINE = "quarantine"


class PolicyReasonSeverity(StrEnum):
    """Severity levels for policy reasons."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class PolicyReason:
    """A single reason supporting a WorldTwin policy decision."""

    code: str
    severity: PolicyReasonSeverity
    message: str
    source: str

    def __post_init__(self) -> None:
        """Validate and normalize a policy reason."""

        object.__setattr__(self, "code", _require_non_empty(self.code, "policy reason code"))
        object.__setattr__(self, "message", _require_non_empty(self.message, "policy message"))
        object.__setattr__(self, "source", _require_non_empty(self.source, "policy source"))

    def canonical_payload(self) -> dict[str, str]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    """A reviewable policy evaluation for a scenario and evidence state."""

    policy_evaluation_id: str
    decision: PolicyDecision
    scenario_id: str
    created_at: datetime
    evaluator: str
    reasons: tuple[PolicyReason, ...]
    assumption_ledger_id: str = ""
    constraint_set_id: str = ""
    schema_version: str = POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a policy evaluation."""

        object.__setattr__(
            self,
            "policy_evaluation_id",
            _require_non_empty(self.policy_evaluation_id, "policy evaluation id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "policy evaluation created_at"),
        )
        object.__setattr__(self, "evaluator", _require_non_empty(self.evaluator, "evaluator"))
        object.__setattr__(self, "reasons", _normalize_reasons(self.reasons))
        object.__setattr__(self, "assumption_ledger_id", self.assumption_ledger_id.strip())
        object.__setattr__(self, "constraint_set_id", self.constraint_set_id.strip())
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "policy schema version"),
        )

    @property
    def allows_execution_review(self) -> bool:
        """Return True when evidence may proceed to human execution review."""

        return self.decision is PolicyDecision.ALLOW

    @property
    def requires_human_caution(self) -> bool:
        """Return True when the evaluation should proceed only with caution."""

        return self.decision is PolicyDecision.CAUTION

    @property
    def blocks_execution_review(self) -> bool:
        """Return True when execution review should be blocked."""

        return self.decision in {PolicyDecision.DENY, PolicyDecision.QUARANTINE}

    def highest_reason_severity(self) -> PolicyReasonSeverity:
        """Return the highest severity among policy reasons."""

        return max((reason.severity for reason in self.reasons), key=_reason_severity_rank)

    def reason_codes(self) -> tuple[str, ...]:
        """Return policy reason codes in deterministic order."""

        return tuple(reason.code for reason in self.reasons)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "assumption_ledger_id": self.assumption_ledger_id,
            "constraint_set_id": self.constraint_set_id,
            "created_at": self.created_at.isoformat(),
            "decision": self.decision.value,
            "evaluator": self.evaluator,
            "policy_evaluation_id": self.policy_evaluation_id,
            "reasons": [reason.canonical_payload() for reason in self.reasons],
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this policy evaluation."""

        return _stable_sha256(self.canonical_payload())


def evaluate_worldtwin_policy(
    *,
    scenario: ScenarioManifest,
    created_at: datetime,
    evaluator: str,
    assumption_ledger: AssumptionLedger | None = None,
    constraint_set: ConstraintSet | None = None,
    predicted_values: Mapping[str, float] | None = None,
    policy_evaluation_id: str | None = None,
) -> PolicyEvaluation:
    """Evaluate a scenario and optional evidence gates into a policy decision."""

    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "policy evaluation created_at",
    )
    normalized_evaluator = _require_non_empty(evaluator, "evaluator")
    values = {} if predicted_values is None else dict(predicted_values)

    reasons: list[PolicyReason] = []
    reasons.extend(_scenario_validation_reasons(scenario))

    if assumption_ledger is None:
        reasons.append(
            PolicyReason(
                code="missing-assumption-ledger",
                severity=PolicyReasonSeverity.WARNING,
                message="No assumption ledger was supplied for policy evaluation.",
                source="assumption-ledger",
            )
        )
        assumption_ledger_id = ""
    else:
        assumption_ledger_id = assumption_ledger.ledger_id
        reasons.extend(_assumption_ledger_reasons(assumption_ledger, normalized_created_at))

    if constraint_set is None:
        reasons.append(
            PolicyReason(
                code="missing-constraint-set",
                severity=PolicyReasonSeverity.WARNING,
                message="No constraint set was supplied for policy evaluation.",
                source="constraint-set",
            )
        )
        constraint_set_id = ""
    else:
        constraint_set_id = constraint_set.constraint_set_id
        reasons.extend(_constraint_reasons(constraint_set, values))

    if not reasons:
        reasons.append(
            PolicyReason(
                code="policy-clean",
                severity=PolicyReasonSeverity.INFO,
                message="Scenario, assumptions, and constraints passed policy evaluation.",
                source="policy",
            )
        )

    decision = _decide_policy(reasons)
    resolved_policy_evaluation_id = policy_evaluation_id or make_policy_evaluation_id(
        decision=decision,
        scenario_id=scenario.scenario_id,
        created_at=normalized_created_at,
        evaluator=normalized_evaluator,
        reasons=tuple(reasons),
        assumption_ledger_id=assumption_ledger_id,
        constraint_set_id=constraint_set_id,
    )

    return PolicyEvaluation(
        policy_evaluation_id=resolved_policy_evaluation_id,
        decision=decision,
        scenario_id=scenario.scenario_id,
        created_at=normalized_created_at,
        evaluator=normalized_evaluator,
        reasons=tuple(reasons),
        assumption_ledger_id=assumption_ledger_id,
        constraint_set_id=constraint_set_id,
    )


def make_policy_evaluation_id(
    *,
    decision: PolicyDecision,
    scenario_id: str,
    created_at: datetime,
    evaluator: str,
    reasons: tuple[PolicyReason, ...],
    assumption_ledger_id: str = "",
    constraint_set_id: str = "",
) -> str:
    """Create a deterministic policy evaluation id."""

    payload = {
        "assumption_ledger_id": assumption_ledger_id.strip(),
        "constraint_set_id": constraint_set_id.strip(),
        "created_at": _require_aware_utc_datetime(
            created_at,
            "policy evaluation created_at",
        ).isoformat(),
        "decision": decision.value,
        "evaluator": _require_non_empty(evaluator, "evaluator"),
        "reasons": [
            reason.canonical_payload() for reason in _normalize_reasons(reasons)
        ],
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": POLICY_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:POLICY_ID_DIGEST_LENGTH]
    return f"policy-evaluation-{digest}"


def _scenario_validation_reasons(scenario: ScenarioManifest) -> tuple[PolicyReason, ...]:
    result = validate_scenario_manifest(scenario)
    reasons: list[PolicyReason] = []

    for issue in result.issues:
        severity = (
            PolicyReasonSeverity.ERROR
            if issue.severity is ScenarioValidationSeverity.ERROR
            else PolicyReasonSeverity.WARNING
        )
        reasons.append(
            PolicyReason(
                code=f"scenario-{issue.code}",
                severity=severity,
                message=issue.message,
                source=f"scenario-validation:{issue.field}",
            )
        )

    return tuple(reasons)


def _assumption_ledger_reasons(
    ledger: AssumptionLedger,
    checked_at: datetime,
) -> tuple[PolicyReason, ...]:
    reasons: list[PolicyReason] = []

    for assumption in ledger.execution_blockers():
        reasons.append(
            PolicyReason(
                code="assumption-missing-required-evidence",
                severity=PolicyReasonSeverity.ERROR,
                message=(
                    f"Assumption '{assumption.name}' requires evidence before execution review."
                ),
                source=f"assumption-ledger:{assumption.assumption_id}",
            )
        )

    for assumption in ledger.disputed_assumptions():
        reasons.append(
            PolicyReason(
                code="assumption-disputed",
                severity=PolicyReasonSeverity.CRITICAL,
                message=f"Assumption '{assumption.name}' is disputed and must be quarantined.",
                source=f"assumption-ledger:{assumption.assumption_id}",
            )
        )

    for assumption in ledger.stale_assumptions_at(checked_at):
        reasons.append(
            PolicyReason(
                code="assumption-stale",
                severity=PolicyReasonSeverity.CRITICAL,
                message=f"Assumption '{assumption.name}' is stale at policy evaluation time.",
                source=f"assumption-ledger:{assumption.assumption_id}",
            )
        )

    if ledger.lowest_confidence() < 0.50:
        reasons.append(
            PolicyReason(
                code="assumption-low-confidence",
                severity=PolicyReasonSeverity.WARNING,
                message="Assumption ledger contains at least one confidence value below 0.50.",
                source=f"assumption-ledger:{ledger.ledger_id}",
            )
        )

    return tuple(reasons)


def _constraint_reasons(
    constraint_set: ConstraintSet,
    values: Mapping[str, float],
) -> tuple[PolicyReason, ...]:
    reasons: list[PolicyReason] = []
    evaluations = constraint_set.evaluate(values)
    hard_failed_rule_ids = set(constraint_set.hard_failed_rule_ids(values))
    decision = evaluations.decision(tuple(sorted(hard_failed_rule_ids)))

    if decision is ConstraintDecision.PASS:
        return ()

    for evaluation in evaluations.failed_evaluations():
        severity = (
            PolicyReasonSeverity.ERROR
            if evaluation.rule_id in hard_failed_rule_ids
            else PolicyReasonSeverity.WARNING
        )
        reasons.append(
            PolicyReason(
                code="constraint-hard-failed"
                if evaluation.rule_id in hard_failed_rule_ids
                else "constraint-soft-failed",
                severity=severity,
                message=evaluation.message,
                source=f"constraint-set:{evaluation.rule_id}",
            )
        )

    return tuple(reasons)


def _decide_policy(reasons: list[PolicyReason]) -> PolicyDecision:
    if any(reason.severity is PolicyReasonSeverity.CRITICAL for reason in reasons):
        return PolicyDecision.QUARANTINE
    if any(reason.severity is PolicyReasonSeverity.ERROR for reason in reasons):
        return PolicyDecision.DENY
    if any(reason.severity is PolicyReasonSeverity.WARNING for reason in reasons):
        return PolicyDecision.CAUTION
    return PolicyDecision.ALLOW


def _normalize_reasons(reasons: tuple[PolicyReason, ...]) -> tuple[PolicyReason, ...]:
    if not reasons:
        raise ValueError("policy evaluation requires at least one reason")

    return tuple(
        sorted(
            reasons,
            key=lambda reason: (
                _reason_severity_rank(reason.severity),
                reason.code,
                reason.source,
                reason.message,
            ),
        )
    )


def _reason_severity_rank(severity: PolicyReasonSeverity) -> int:
    ranks = {
        PolicyReasonSeverity.INFO: 0,
        PolicyReasonSeverity.WARNING: 1,
        PolicyReasonSeverity.ERROR: 2,
        PolicyReasonSeverity.CRITICAL: 3,
    }
    return ranks[severity]


def _require_non_empty(value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")
    return normalized_value


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()

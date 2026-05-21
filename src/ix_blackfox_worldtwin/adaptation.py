"""Adaptation gates for IX-BlackFox-WorldTwin.

Adaptation is where a world model could become dangerous if learning is allowed
to turn into silent mutation. This module keeps adaptation proposals bounded,
evidence-linked, confidence-aware, receipt-chain-aware, and human-review-only.
It never authorizes automatic model or runtime changes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.model_confidence import ModelConfidenceProfile, ModelTrustTier
from ix_blackfox_worldtwin.policy import PolicyDecision, PolicyEvaluation
from ix_blackfox_worldtwin.reality_delta import RealityDeltaReport, RealityDeltaVerdict
from ix_blackfox_worldtwin.receipt_chain import (
    ReceiptChainValidationResult,
    ReceiptChainValidationStatus,
)

ADAPTATION_SCHEMA_VERSION = "adaptation-gate-v1"
ADAPTATION_GATE_ID_DIGEST_LENGTH = 16


class AdaptationScope(StrEnum):
    """Supported scopes for an adaptation candidate."""

    SIMULATION_RULE = "simulation-rule"
    MODEL_CONFIDENCE = "model-confidence"
    SCENARIO_TEMPLATE = "scenario-template"
    POLICY_THRESHOLD = "policy-threshold"
    KERNEL_CONFIGURATION = "kernel-configuration"


class AdaptationDecision(StrEnum):
    """Decision emitted by the adaptation gate."""

    READY_FOR_HUMAN_REVIEW = "ready-for-human-review"
    CAUTION_REVIEW = "caution-review"
    DENY = "deny"
    QUARANTINE = "quarantine"


class AdaptationReasonSeverity(StrEnum):
    """Severity levels for adaptation gate reasons."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AdaptationCandidate:
    """A proposed bounded change to a WorldTwin model, rule, policy, or kernel."""

    candidate_id: str
    model_id: str
    scope: AdaptationScope
    target_artifact_id: str
    summary: str
    proposed_change_fingerprint: str
    created_at: datetime
    proposed_by: str
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    requires_human_authority: bool = True
    schema_version: str = ADAPTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize an adaptation candidate."""

        if not self.requires_human_authority:
            raise ValueError("adaptation candidate must require human authority")

        object.__setattr__(
            self,
            "candidate_id",
            _require_non_empty(self.candidate_id, "candidate id"),
        )
        object.__setattr__(self, "model_id", _require_non_empty(self.model_id, "model id"))
        object.__setattr__(
            self,
            "target_artifact_id",
            _require_non_empty(self.target_artifact_id, "target artifact id"),
        )
        object.__setattr__(self, "summary", _require_non_empty(self.summary, "summary"))
        object.__setattr__(
            self,
            "proposed_change_fingerprint",
            _require_non_empty(
                self.proposed_change_fingerprint,
                "proposed change fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "candidate created_at"),
        )
        object.__setattr__(self, "proposed_by", _require_non_empty(self.proposed_by, "proposed by"))
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_unique_text_tuple(self.evidence_ids, "evidence id"),
        )
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "candidate tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "adaptation schema version"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "candidate_id": self.candidate_id,
            "created_at": self.created_at.isoformat(),
            "evidence_ids": list(self.evidence_ids),
            "model_id": self.model_id,
            "proposed_by": self.proposed_by,
            "proposed_change_fingerprint": self.proposed_change_fingerprint,
            "requires_human_authority": self.requires_human_authority,
            "schema_version": self.schema_version,
            "scope": self.scope.value,
            "summary": self.summary,
            "tags": list(self.tags),
            "target_artifact_id": self.target_artifact_id,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this candidate."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class AdaptationGateReason:
    """A single reason supporting an adaptation gate result."""

    code: str
    severity: AdaptationReasonSeverity
    message: str
    source: str

    def __post_init__(self) -> None:
        """Validate and normalize an adaptation gate reason."""

        object.__setattr__(self, "code", _require_non_empty(self.code, "reason code"))
        object.__setattr__(self, "message", _require_non_empty(self.message, "reason message"))
        object.__setattr__(self, "source", _require_non_empty(self.source, "reason source"))

    def canonical_payload(self) -> dict[str, str]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class AdaptationGateResult:
    """Result of evaluating whether an adaptation may enter human review."""

    gate_result_id: str
    candidate_id: str
    model_id: str
    decision: AdaptationDecision
    created_at: datetime
    evaluated_by: str
    reasons: tuple[AdaptationGateReason, ...]
    confidence_profile_id: str
    reality_delta_report_id: str = ""
    receipt_chain_validation_status: str = ""
    policy_evaluation_id: str = ""
    requires_human_authority: bool = True
    allowed_for_automatic_application: bool = False
    schema_version: str = ADAPTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize an adaptation gate result."""

        if not self.requires_human_authority:
            raise ValueError("adaptation gate result must require human authority")
        if self.allowed_for_automatic_application:
            raise ValueError("adaptation gate must never allow automatic application")
        if not self.reasons:
            raise ValueError("adaptation gate result requires at least one reason")

        object.__setattr__(
            self,
            "gate_result_id",
            _require_non_empty(self.gate_result_id, "gate result id"),
        )
        object.__setattr__(
            self,
            "candidate_id",
            _require_non_empty(self.candidate_id, "candidate id"),
        )
        object.__setattr__(self, "model_id", _require_non_empty(self.model_id, "model id"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "gate result created_at"),
        )
        object.__setattr__(self, "evaluated_by", _require_non_empty(self.evaluated_by, "evaluated by"))
        object.__setattr__(self, "reasons", _normalize_gate_reasons(self.reasons))
        object.__setattr__(
            self,
            "confidence_profile_id",
            _require_non_empty(self.confidence_profile_id, "confidence profile id"),
        )
        object.__setattr__(self, "reality_delta_report_id", self.reality_delta_report_id.strip())
        object.__setattr__(
            self,
            "receipt_chain_validation_status",
            self.receipt_chain_validation_status.strip(),
        )
        object.__setattr__(self, "policy_evaluation_id", self.policy_evaluation_id.strip())
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "adaptation schema version"),
        )

        expected_decision = decide_adaptation_from_reasons(self.reasons)
        if self.decision is not expected_decision:
            raise ValueError("adaptation decision must match reason severity state")

    @property
    def may_enter_human_review(self) -> bool:
        """Return True when the candidate may enter human adaptation review."""

        return self.decision in {
            AdaptationDecision.READY_FOR_HUMAN_REVIEW,
            AdaptationDecision.CAUTION_REVIEW,
        }

    @property
    def blocks_adaptation_review(self) -> bool:
        """Return True when adaptation review should be blocked."""

        return self.decision in {AdaptationDecision.DENY, AdaptationDecision.QUARANTINE}

    def highest_reason_severity(self) -> AdaptationReasonSeverity:
        """Return the highest reason severity."""

        return max((reason.severity for reason in self.reasons), key=_severity_rank)

    def reason_codes(self) -> tuple[str, ...]:
        """Return reason codes in deterministic order."""

        return tuple(reason.code for reason in self.reasons)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and handoff."""

        return {
            "allowed_for_automatic_application": self.allowed_for_automatic_application,
            "candidate_id": self.candidate_id,
            "confidence_profile_id": self.confidence_profile_id,
            "created_at": self.created_at.isoformat(),
            "decision": self.decision.value,
            "evaluated_by": self.evaluated_by,
            "gate_result_id": self.gate_result_id,
            "model_id": self.model_id,
            "policy_evaluation_id": self.policy_evaluation_id,
            "reality_delta_report_id": self.reality_delta_report_id,
            "reasons": [reason.canonical_payload() for reason in self.reasons],
            "receipt_chain_validation_status": self.receipt_chain_validation_status,
            "requires_human_authority": self.requires_human_authority,
            "schema_version": self.schema_version,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this gate result."""

        return _stable_sha256(self.canonical_payload())


def create_adaptation_candidate(
    *,
    model_id: str,
    scope: AdaptationScope,
    target_artifact_id: str,
    summary: str,
    proposed_change_fingerprint: str,
    created_at: datetime,
    proposed_by: str,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    candidate_id: str | None = None,
) -> AdaptationCandidate:
    """Create a bounded adaptation candidate with a deterministic id."""

    normalized_model_id = _require_non_empty(model_id, "model id")
    normalized_target = _require_non_empty(target_artifact_id, "target artifact id")
    normalized_summary = _require_non_empty(summary, "summary")
    normalized_fingerprint = _require_non_empty(
        proposed_change_fingerprint,
        "proposed change fingerprint",
    )
    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "candidate created_at",
    )
    normalized_proposed_by = _require_non_empty(proposed_by, "proposed by")
    normalized_evidence_ids = _normalize_unique_text_tuple(evidence_ids, "evidence id")
    normalized_tags = _normalize_unique_text_tuple(tags, "candidate tag")
    resolved_candidate_id = candidate_id or make_adaptation_candidate_id(
        model_id=normalized_model_id,
        scope=scope,
        target_artifact_id=normalized_target,
        summary=normalized_summary,
        proposed_change_fingerprint=normalized_fingerprint,
        created_at=normalized_created_at,
        proposed_by=normalized_proposed_by,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
    )

    return AdaptationCandidate(
        candidate_id=resolved_candidate_id,
        model_id=normalized_model_id,
        scope=scope,
        target_artifact_id=normalized_target,
        summary=normalized_summary,
        proposed_change_fingerprint=normalized_fingerprint,
        created_at=normalized_created_at,
        proposed_by=normalized_proposed_by,
        evidence_ids=normalized_evidence_ids,
        tags=normalized_tags,
    )


def evaluate_adaptation_gate(
    *,
    candidate: AdaptationCandidate,
    confidence_profile: ModelConfidenceProfile,
    created_at: datetime,
    evaluated_by: str,
    reality_delta_report: RealityDeltaReport | None = None,
    receipt_chain_validation: ReceiptChainValidationResult | None = None,
    policy_evaluation: PolicyEvaluation | None = None,
    gate_result_id: str | None = None,
) -> AdaptationGateResult:
    """Evaluate whether an adaptation candidate may enter human review."""

    if candidate.model_id != confidence_profile.model_id:
        raise ValueError("candidate model_id must match confidence profile model_id")

    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "gate result created_at",
    )
    normalized_evaluated_by = _require_non_empty(evaluated_by, "evaluated by")
    reasons: list[AdaptationGateReason] = [
        AdaptationGateReason(
            code="human-authority-required",
            severity=AdaptationReasonSeverity.INFO,
            message="Adaptation candidate is review-only and requires human authority.",
            source=f"candidate:{candidate.candidate_id}",
        )
    ]

    if not candidate.evidence_ids:
        reasons.append(
            AdaptationGateReason(
                code="candidate-missing-evidence",
                severity=AdaptationReasonSeverity.WARNING,
                message="Adaptation candidate has no explicit supporting evidence ids.",
                source=f"candidate:{candidate.candidate_id}",
            )
        )

    reasons.extend(_confidence_reasons(confidence_profile))
    reasons.extend(_reality_delta_reasons(reality_delta_report))
    reasons.extend(_receipt_chain_reasons(receipt_chain_validation))
    reasons.extend(_policy_reasons(policy_evaluation))

    normalized_reasons = _normalize_gate_reasons(tuple(reasons))
    decision = decide_adaptation_from_reasons(normalized_reasons)
    resolved_gate_result_id = gate_result_id or make_adaptation_gate_result_id(
        candidate_id=candidate.candidate_id,
        model_id=candidate.model_id,
        decision=decision,
        created_at=normalized_created_at,
        evaluated_by=normalized_evaluated_by,
        reasons=normalized_reasons,
        confidence_profile_id=confidence_profile.profile_id,
        reality_delta_report_id="" if reality_delta_report is None else reality_delta_report.report_id,
        receipt_chain_validation_status=(
            "" if receipt_chain_validation is None else receipt_chain_validation.status.value
        ),
        policy_evaluation_id=(
            "" if policy_evaluation is None else policy_evaluation.policy_evaluation_id
        ),
    )

    return AdaptationGateResult(
        gate_result_id=resolved_gate_result_id,
        candidate_id=candidate.candidate_id,
        model_id=candidate.model_id,
        decision=decision,
        created_at=normalized_created_at,
        evaluated_by=normalized_evaluated_by,
        reasons=normalized_reasons,
        confidence_profile_id=confidence_profile.profile_id,
        reality_delta_report_id="" if reality_delta_report is None else reality_delta_report.report_id,
        receipt_chain_validation_status=(
            "" if receipt_chain_validation is None else receipt_chain_validation.status.value
        ),
        policy_evaluation_id=(
            "" if policy_evaluation is None else policy_evaluation.policy_evaluation_id
        ),
    )


def decide_adaptation_from_reasons(
    reasons: tuple[AdaptationGateReason, ...],
) -> AdaptationDecision:
    """Derive an adaptation decision from reason severities."""

    normalized_reasons = _normalize_gate_reasons(reasons)
    if any(reason.severity is AdaptationReasonSeverity.CRITICAL for reason in normalized_reasons):
        return AdaptationDecision.QUARANTINE
    if any(reason.severity is AdaptationReasonSeverity.ERROR for reason in normalized_reasons):
        return AdaptationDecision.DENY
    if any(reason.severity is AdaptationReasonSeverity.WARNING for reason in normalized_reasons):
        return AdaptationDecision.CAUTION_REVIEW
    return AdaptationDecision.READY_FOR_HUMAN_REVIEW


def make_adaptation_candidate_id(
    *,
    model_id: str,
    scope: AdaptationScope,
    target_artifact_id: str,
    summary: str,
    proposed_change_fingerprint: str,
    created_at: datetime,
    proposed_by: str,
    evidence_ids: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> str:
    """Create a deterministic adaptation candidate id."""

    payload = {
        "created_at": _require_aware_utc_datetime(
            created_at,
            "candidate created_at",
        ).isoformat(),
        "evidence_ids": list(_normalize_unique_text_tuple(evidence_ids, "evidence id")),
        "model_id": _require_non_empty(model_id, "model id"),
        "proposed_by": _require_non_empty(proposed_by, "proposed by"),
        "proposed_change_fingerprint": _require_non_empty(
            proposed_change_fingerprint,
            "proposed change fingerprint",
        ),
        "requires_human_authority": True,
        "schema_version": ADAPTATION_SCHEMA_VERSION,
        "scope": scope.value,
        "summary": _require_non_empty(summary, "summary"),
        "tags": list(_normalize_unique_text_tuple(tags, "candidate tag")),
        "target_artifact_id": _require_non_empty(target_artifact_id, "target artifact id"),
    }
    digest = _stable_sha256(payload)[:ADAPTATION_GATE_ID_DIGEST_LENGTH]
    return f"adaptation-candidate-{digest}"


def make_adaptation_gate_result_id(
    *,
    candidate_id: str,
    model_id: str,
    decision: AdaptationDecision,
    created_at: datetime,
    evaluated_by: str,
    reasons: tuple[AdaptationGateReason, ...],
    confidence_profile_id: str,
    reality_delta_report_id: str = "",
    receipt_chain_validation_status: str = "",
    policy_evaluation_id: str = "",
) -> str:
    """Create a deterministic adaptation gate result id."""

    payload = {
        "allowed_for_automatic_application": False,
        "candidate_id": _require_non_empty(candidate_id, "candidate id"),
        "confidence_profile_id": _require_non_empty(
            confidence_profile_id,
            "confidence profile id",
        ),
        "created_at": _require_aware_utc_datetime(
            created_at,
            "gate result created_at",
        ).isoformat(),
        "decision": decision.value,
        "evaluated_by": _require_non_empty(evaluated_by, "evaluated by"),
        "model_id": _require_non_empty(model_id, "model id"),
        "policy_evaluation_id": policy_evaluation_id.strip(),
        "reality_delta_report_id": reality_delta_report_id.strip(),
        "reasons": [
            reason.canonical_payload() for reason in _normalize_gate_reasons(reasons)
        ],
        "receipt_chain_validation_status": receipt_chain_validation_status.strip(),
        "requires_human_authority": True,
        "schema_version": ADAPTATION_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:ADAPTATION_GATE_ID_DIGEST_LENGTH]
    return f"adaptation-gate-result-{digest}"


def _confidence_reasons(
    confidence_profile: ModelConfidenceProfile,
) -> tuple[AdaptationGateReason, ...]:
    if confidence_profile.trust_tier is ModelTrustTier.TRUSTED:
        severity = AdaptationReasonSeverity.INFO
        code = "model-trusted"
    elif confidence_profile.trust_tier is ModelTrustTier.CANDIDATE:
        severity = AdaptationReasonSeverity.WARNING
        code = "model-candidate-only"
    elif confidence_profile.trust_tier is ModelTrustTier.WATCHLIST:
        severity = AdaptationReasonSeverity.ERROR
        code = "model-watchlist"
    else:
        severity = AdaptationReasonSeverity.CRITICAL
        code = "model-confidence-blocks-adaptation"

    return (
        AdaptationGateReason(
            code=code,
            severity=severity,
            message=(
                "Model confidence profile trust tier is "
                f"{confidence_profile.trust_tier.value} with score "
                f"{confidence_profile.confidence_score:.6f}."
            ),
            source=f"model-confidence:{confidence_profile.profile_id}",
        ),
    )


def _reality_delta_reasons(
    report: RealityDeltaReport | None,
) -> tuple[AdaptationGateReason, ...]:
    if report is None:
        return (
            AdaptationGateReason(
                code="reality-delta-missing",
                severity=AdaptationReasonSeverity.WARNING,
                message="No reality-delta report was supplied for adaptation review.",
                source="reality-delta",
            ),
        )

    if report.verdict is RealityDeltaVerdict.MATCH:
        severity = AdaptationReasonSeverity.INFO
    elif report.verdict is RealityDeltaVerdict.DRIFT:
        severity = AdaptationReasonSeverity.WARNING
    elif report.verdict is RealityDeltaVerdict.BREACH:
        severity = AdaptationReasonSeverity.ERROR
    else:
        severity = AdaptationReasonSeverity.CRITICAL

    return (
        AdaptationGateReason(
            code=f"reality-delta-{report.verdict.value}",
            severity=severity,
            message=f"Reality-delta verdict is {report.verdict.value}.",
            source=f"reality-delta:{report.report_id}",
        ),
    )


def _receipt_chain_reasons(
    validation: ReceiptChainValidationResult | None,
) -> tuple[AdaptationGateReason, ...]:
    if validation is None:
        return (
            AdaptationGateReason(
                code="receipt-chain-validation-missing",
                severity=AdaptationReasonSeverity.WARNING,
                message="No receipt-chain validation result was supplied.",
                source="receipt-chain",
            ),
        )

    if validation.status is ReceiptChainValidationStatus.PASS:
        return (
            AdaptationGateReason(
                code="receipt-chain-valid",
                severity=AdaptationReasonSeverity.INFO,
                message="Receipt chain validation passed.",
                source=f"receipt-chain:{validation.chain_id}",
            ),
        )

    return (
        AdaptationGateReason(
            code="receipt-chain-invalid",
            severity=AdaptationReasonSeverity.ERROR,
            message="Receipt chain validation failed and must be repaired before adaptation review.",
            source=f"receipt-chain:{validation.chain_id}",
        ),
    )


def _policy_reasons(policy: PolicyEvaluation | None) -> tuple[AdaptationGateReason, ...]:
    if policy is None:
        return (
            AdaptationGateReason(
                code="policy-evaluation-missing",
                severity=AdaptationReasonSeverity.WARNING,
                message="No policy evaluation was supplied for adaptation review.",
                source="policy",
            ),
        )

    if policy.decision is PolicyDecision.ALLOW:
        severity = AdaptationReasonSeverity.INFO
    elif policy.decision is PolicyDecision.CAUTION:
        severity = AdaptationReasonSeverity.WARNING
    elif policy.decision is PolicyDecision.DENY:
        severity = AdaptationReasonSeverity.ERROR
    else:
        severity = AdaptationReasonSeverity.CRITICAL

    return (
        AdaptationGateReason(
            code=f"policy-{policy.decision.value}",
            severity=severity,
            message=f"Policy evaluation decision is {policy.decision.value}.",
            source=f"policy:{policy.policy_evaluation_id}",
        ),
    )


def _normalize_gate_reasons(
    reasons: tuple[AdaptationGateReason, ...],
) -> tuple[AdaptationGateReason, ...]:
    if not reasons:
        raise ValueError("adaptation gate result requires at least one reason")

    return tuple(
        sorted(
            reasons,
            key=lambda reason: (
                _severity_rank(reason.severity),
                reason.code,
                reason.source,
                reason.message,
            ),
        )
    )


def _severity_rank(severity: AdaptationReasonSeverity) -> int:
    ranks = {
        AdaptationReasonSeverity.INFO: 0,
        AdaptationReasonSeverity.WARNING: 1,
        AdaptationReasonSeverity.ERROR: 2,
        AdaptationReasonSeverity.CRITICAL: 3,
    }
    return ranks[severity]


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


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()

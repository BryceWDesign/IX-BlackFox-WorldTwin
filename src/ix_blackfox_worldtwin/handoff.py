"""Human-reviewable handoff packages for IX-BlackFox-WorldTwin.

A handoff package is the boundary object that carries WorldTwin evidence toward
a governed execution system. It never authorizes execution. It preserves the
scenario, prediction, receipt, receipt-chain, policy, confidence, reality-delta,
and adaptation-gate state so a human reviewer can inspect exactly what is being
asked for and why.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.adaptation import AdaptationDecision, AdaptationGateResult
from ix_blackfox_worldtwin.model_confidence import ModelConfidenceProfile
from ix_blackfox_worldtwin.policy import PolicyDecision, PolicyEvaluation
from ix_blackfox_worldtwin.prediction import PredictionDisposition, PredictionResult
from ix_blackfox_worldtwin.reality_delta import RealityDeltaReport, RealityDeltaVerdict
from ix_blackfox_worldtwin.receipt_chain import (
    ReceiptChain,
    ReceiptChainValidationResult,
    ReceiptChainValidationStatus,
)
from ix_blackfox_worldtwin.receipts import PredictionReceipt, ReceiptReviewDecision

HANDOFF_SCHEMA_VERSION = "human-review-handoff-v1"
HANDOFF_ID_DIGEST_LENGTH = 16


class HandoffTarget(StrEnum):
    """Supported downstream targets for a WorldTwin handoff."""

    BLACKFOX_EXECUTION_GOVERNANCE = "blackfox-execution-governance"
    HUMAN_REVIEW_QUEUE = "human-review-queue"
    EXTERNAL_AUDIT_PACKET = "external-audit-packet"


class HandoffDecision(StrEnum):
    """Decision encoded by a handoff package."""

    READY_FOR_REVIEW = "ready-for-review"
    CAUTION_REVIEW = "caution-review"
    BLOCKED = "blocked"
    QUARANTINED = "quarantined"


class HandoffReasonSeverity(StrEnum):
    """Severity levels for handoff reasons."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class HandoffArtifact:
    """A fingerprinted artifact included in a handoff package."""

    artifact_id: str
    artifact_type: str
    fingerprint: str
    source: str

    def __post_init__(self) -> None:
        """Validate and normalize a handoff artifact."""

        object.__setattr__(self, "artifact_id", _require_non_empty(self.artifact_id, "artifact id"))
        object.__setattr__(
            self,
            "artifact_type",
            _require_non_empty(self.artifact_type, "artifact type"),
        )
        object.__setattr__(
            self,
            "fingerprint",
            _require_non_empty(self.fingerprint, "artifact fingerprint"),
        )
        object.__setattr__(self, "source", _require_non_empty(self.source, "artifact source"))

    def canonical_payload(self) -> dict[str, str]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "fingerprint": self.fingerprint,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class HandoffReason:
    """A reason supporting a WorldTwin handoff decision."""

    code: str
    severity: HandoffReasonSeverity
    message: str
    source: str

    def __post_init__(self) -> None:
        """Validate and normalize a handoff reason."""

        object.__setattr__(self, "code", _require_non_empty(self.code, "handoff reason code"))
        object.__setattr__(
            self,
            "message",
            _require_non_empty(self.message, "handoff reason message"),
        )
        object.__setattr__(self, "source", _require_non_empty(self.source, "handoff source"))

    def canonical_payload(self) -> dict[str, str]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class HandoffPackage:
    """A bounded, human-reviewable WorldTwin handoff package."""

    handoff_id: str
    target: HandoffTarget
    decision: HandoffDecision
    scenario_id: str
    prediction_id: str
    receipt_id: str
    receipt_chain_id: str
    created_at: datetime
    created_by: str
    requested_action: str
    reasons: tuple[HandoffReason, ...]
    artifacts: tuple[HandoffArtifact, ...]
    policy_evaluation_id: str = ""
    adaptation_gate_result_id: str = ""
    reality_delta_report_id: str = ""
    model_confidence_profile_id: str = ""
    requires_human_authority: bool = True
    allowed_for_automatic_execution: bool = False
    notes: tuple[str, ...] = ()
    schema_version: str = HANDOFF_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a handoff package."""

        if not self.requires_human_authority:
            raise ValueError("handoff package must require human authority")
        if self.allowed_for_automatic_execution:
            raise ValueError("handoff package must never allow automatic execution")
        if not self.reasons:
            raise ValueError("handoff package requires at least one reason")
        if not self.artifacts:
            raise ValueError("handoff package requires at least one artifact")

        object.__setattr__(self, "handoff_id", _require_non_empty(self.handoff_id, "handoff id"))
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "prediction_id",
            _require_non_empty(self.prediction_id, "prediction id"),
        )
        object.__setattr__(self, "receipt_id", _require_non_empty(self.receipt_id, "receipt id"))
        object.__setattr__(
            self,
            "receipt_chain_id",
            _require_non_empty(self.receipt_chain_id, "receipt chain id"),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "handoff created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "requested_action",
            _require_non_empty(self.requested_action, "requested action"),
        )
        object.__setattr__(self, "reasons", _normalize_handoff_reasons(self.reasons))
        object.__setattr__(self, "artifacts", _normalize_handoff_artifacts(self.artifacts))
        object.__setattr__(self, "policy_evaluation_id", self.policy_evaluation_id.strip())
        object.__setattr__(
            self,
            "adaptation_gate_result_id",
            self.adaptation_gate_result_id.strip(),
        )
        object.__setattr__(self, "reality_delta_report_id", self.reality_delta_report_id.strip())
        object.__setattr__(
            self,
            "model_confidence_profile_id",
            self.model_confidence_profile_id.strip(),
        )
        object.__setattr__(self, "notes", _normalize_unique_text_tuple(self.notes, "handoff note"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "handoff schema version"),
        )

        expected_decision = decide_handoff_from_reasons(self.reasons)
        if self.decision is not expected_decision:
            raise ValueError("handoff decision must match reason severity state")

    @property
    def may_enter_human_review(self) -> bool:
        """Return True when the package may enter human review."""

        return self.decision in {
            HandoffDecision.READY_FOR_REVIEW,
            HandoffDecision.CAUTION_REVIEW,
        }

    @property
    def blocks_downstream_review(self) -> bool:
        """Return True when the package blocks downstream review."""

        return self.decision in {HandoffDecision.BLOCKED, HandoffDecision.QUARANTINED}

    def reason_codes(self) -> tuple[str, ...]:
        """Return reason codes in deterministic order."""

        return tuple(reason.code for reason in self.reasons)

    def artifact_table(self) -> dict[str, str]:
        """Return artifact ids mapped to fingerprints."""

        return {artifact.artifact_id: artifact.fingerprint for artifact in self.artifacts}

    def highest_reason_severity(self) -> HandoffReasonSeverity:
        """Return the highest handoff reason severity."""

        return max((reason.severity for reason in self.reasons), key=_severity_rank)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and downstream review."""

        return {
            "adaptation_gate_result_id": self.adaptation_gate_result_id,
            "allowed_for_automatic_execution": self.allowed_for_automatic_execution,
            "artifacts": [artifact.canonical_payload() for artifact in self.artifacts],
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "decision": self.decision.value,
            "handoff_id": self.handoff_id,
            "model_confidence_profile_id": self.model_confidence_profile_id,
            "notes": list(self.notes),
            "policy_evaluation_id": self.policy_evaluation_id,
            "prediction_id": self.prediction_id,
            "reality_delta_report_id": self.reality_delta_report_id,
            "reasons": [reason.canonical_payload() for reason in self.reasons],
            "receipt_chain_id": self.receipt_chain_id,
            "receipt_id": self.receipt_id,
            "requested_action": self.requested_action,
            "requires_human_authority": self.requires_human_authority,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "target": self.target.value,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this handoff package."""

        return _stable_sha256(self.canonical_payload())


def create_handoff_package(
    *,
    target: HandoffTarget,
    prediction: PredictionResult,
    receipt: PredictionReceipt,
    receipt_chain: ReceiptChain,
    receipt_chain_validation: ReceiptChainValidationResult,
    created_at: datetime,
    created_by: str,
    requested_action: str,
    policy_evaluation: PolicyEvaluation | None = None,
    adaptation_gate_result: AdaptationGateResult | None = None,
    reality_delta_report: RealityDeltaReport | None = None,
    model_confidence_profile: ModelConfidenceProfile | None = None,
    notes: tuple[str, ...] = (),
    handoff_id: str | None = None,
) -> HandoffPackage:
    """Create a human-reviewable handoff package from WorldTwin evidence."""

    _validate_core_linkage(
        prediction=prediction,
        receipt=receipt,
        receipt_chain=receipt_chain,
        receipt_chain_validation=receipt_chain_validation,
        policy_evaluation=policy_evaluation,
        adaptation_gate_result=adaptation_gate_result,
        reality_delta_report=reality_delta_report,
    )

    normalized_created_at = _require_aware_utc_datetime(created_at, "handoff created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_requested_action = _require_non_empty(requested_action, "requested action")
    normalized_notes = _normalize_unique_text_tuple(notes, "handoff note")
    reasons = _build_handoff_reasons(
        prediction=prediction,
        receipt=receipt,
        receipt_chain_validation=receipt_chain_validation,
        policy_evaluation=policy_evaluation,
        adaptation_gate_result=adaptation_gate_result,
        reality_delta_report=reality_delta_report,
        model_confidence_profile=model_confidence_profile,
    )
    artifacts = _build_handoff_artifacts(
        prediction=prediction,
        receipt=receipt,
        receipt_chain=receipt_chain,
        receipt_chain_validation=receipt_chain_validation,
        policy_evaluation=policy_evaluation,
        adaptation_gate_result=adaptation_gate_result,
        reality_delta_report=reality_delta_report,
        model_confidence_profile=model_confidence_profile,
    )
    decision = decide_handoff_from_reasons(reasons)
    resolved_handoff_id = handoff_id or make_handoff_package_id(
        target=target,
        decision=decision,
        scenario_id=prediction.scenario_id,
        prediction_id=prediction.prediction_id,
        receipt_id=receipt.receipt_id,
        receipt_chain_id=receipt_chain.chain_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        requested_action=normalized_requested_action,
        reasons=reasons,
        artifacts=artifacts,
        policy_evaluation_id=(
            "" if policy_evaluation is None else policy_evaluation.policy_evaluation_id
        ),
        adaptation_gate_result_id=(
            "" if adaptation_gate_result is None else adaptation_gate_result.gate_result_id
        ),
        reality_delta_report_id=""
        if reality_delta_report is None
        else reality_delta_report.report_id,
        model_confidence_profile_id=(
            "" if model_confidence_profile is None else model_confidence_profile.profile_id
        ),
        notes=normalized_notes,
    )

    return HandoffPackage(
        handoff_id=resolved_handoff_id,
        target=target,
        decision=decision,
        scenario_id=prediction.scenario_id,
        prediction_id=prediction.prediction_id,
        receipt_id=receipt.receipt_id,
        receipt_chain_id=receipt_chain.chain_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        requested_action=normalized_requested_action,
        reasons=reasons,
        artifacts=artifacts,
        policy_evaluation_id=(
            "" if policy_evaluation is None else policy_evaluation.policy_evaluation_id
        ),
        adaptation_gate_result_id=(
            "" if adaptation_gate_result is None else adaptation_gate_result.gate_result_id
        ),
        reality_delta_report_id=""
        if reality_delta_report is None
        else reality_delta_report.report_id,
        model_confidence_profile_id=(
            "" if model_confidence_profile is None else model_confidence_profile.profile_id
        ),
        notes=normalized_notes,
    )


def decide_handoff_from_reasons(reasons: tuple[HandoffReason, ...]) -> HandoffDecision:
    """Derive a handoff decision from reason severities."""

    normalized_reasons = _normalize_handoff_reasons(reasons)
    if any(reason.severity is HandoffReasonSeverity.CRITICAL for reason in normalized_reasons):
        return HandoffDecision.QUARANTINED
    if any(reason.severity is HandoffReasonSeverity.ERROR for reason in normalized_reasons):
        return HandoffDecision.BLOCKED
    if any(reason.severity is HandoffReasonSeverity.WARNING for reason in normalized_reasons):
        return HandoffDecision.CAUTION_REVIEW
    return HandoffDecision.READY_FOR_REVIEW


def make_handoff_package_id(
    *,
    target: HandoffTarget,
    decision: HandoffDecision,
    scenario_id: str,
    prediction_id: str,
    receipt_id: str,
    receipt_chain_id: str,
    created_at: datetime,
    created_by: str,
    requested_action: str,
    reasons: tuple[HandoffReason, ...],
    artifacts: tuple[HandoffArtifact, ...],
    policy_evaluation_id: str = "",
    adaptation_gate_result_id: str = "",
    reality_delta_report_id: str = "",
    model_confidence_profile_id: str = "",
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic handoff package id."""

    payload = {
        "adaptation_gate_result_id": adaptation_gate_result_id.strip(),
        "allowed_for_automatic_execution": False,
        "artifacts": [
            artifact.canonical_payload() for artifact in _normalize_handoff_artifacts(artifacts)
        ],
        "created_at": _require_aware_utc_datetime(created_at, "handoff created_at").isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "decision": decision.value,
        "model_confidence_profile_id": model_confidence_profile_id.strip(),
        "notes": list(_normalize_unique_text_tuple(notes, "handoff note")),
        "policy_evaluation_id": policy_evaluation_id.strip(),
        "prediction_id": _require_non_empty(prediction_id, "prediction id"),
        "reality_delta_report_id": reality_delta_report_id.strip(),
        "reasons": [reason.canonical_payload() for reason in _normalize_handoff_reasons(reasons)],
        "receipt_chain_id": _require_non_empty(receipt_chain_id, "receipt chain id"),
        "receipt_id": _require_non_empty(receipt_id, "receipt id"),
        "requested_action": _require_non_empty(requested_action, "requested action"),
        "requires_human_authority": True,
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "target": target.value,
    }
    digest = _stable_sha256(payload)[:HANDOFF_ID_DIGEST_LENGTH]
    return f"handoff-{digest}"


def _validate_core_linkage(
    *,
    prediction: PredictionResult,
    receipt: PredictionReceipt,
    receipt_chain: ReceiptChain,
    receipt_chain_validation: ReceiptChainValidationResult,
    policy_evaluation: PolicyEvaluation | None,
    adaptation_gate_result: AdaptationGateResult | None,
    reality_delta_report: RealityDeltaReport | None,
) -> None:
    if receipt.prediction_id != prediction.prediction_id:
        raise ValueError("receipt prediction_id must match prediction prediction_id")
    if receipt.scenario_id != prediction.scenario_id:
        raise ValueError("receipt scenario_id must match prediction scenario_id")
    if receipt.simulation_id != prediction.simulation_id:
        raise ValueError("receipt simulation_id must match prediction simulation_id")
    if receipt.receipt_id not in receipt_chain.receipt_ids():
        raise ValueError("receipt chain must contain the handoff receipt")
    if receipt_chain_validation.chain_id != receipt_chain.chain_id:
        raise ValueError("receipt-chain validation must match receipt chain id")
    if policy_evaluation is not None and policy_evaluation.scenario_id != prediction.scenario_id:
        raise ValueError("policy evaluation scenario_id must match prediction scenario_id")
    if (
        adaptation_gate_result is not None
        and adaptation_gate_result.policy_evaluation_id
        and policy_evaluation is not None
        and adaptation_gate_result.policy_evaluation_id != policy_evaluation.policy_evaluation_id
    ):
        raise ValueError("adaptation gate policy_evaluation_id must match policy evaluation id")
    if (
        reality_delta_report is not None
        and reality_delta_report.prediction_id != prediction.prediction_id
    ):
        raise ValueError("reality-delta prediction_id must match prediction prediction_id")


def _build_handoff_reasons(
    *,
    prediction: PredictionResult,
    receipt: PredictionReceipt,
    receipt_chain_validation: ReceiptChainValidationResult,
    policy_evaluation: PolicyEvaluation | None,
    adaptation_gate_result: AdaptationGateResult | None,
    reality_delta_report: RealityDeltaReport | None,
    model_confidence_profile: ModelConfidenceProfile | None,
) -> tuple[HandoffReason, ...]:
    reasons: list[HandoffReason] = [
        HandoffReason(
            code="human-authority-required",
            severity=HandoffReasonSeverity.INFO,
            message="Handoff package is review-only and requires human authority.",
            source=f"prediction:{prediction.prediction_id}",
        )
    ]

    reasons.append(_prediction_reason(prediction))
    reasons.append(_receipt_reason(receipt))
    reasons.append(_receipt_chain_reason(receipt_chain_validation))

    if policy_evaluation is None:
        reasons.append(
            HandoffReason(
                code="policy-evaluation-missing",
                severity=HandoffReasonSeverity.WARNING,
                message="No policy evaluation was attached to the handoff package.",
                source="policy",
            )
        )
    else:
        reasons.append(_policy_reason(policy_evaluation))

    if adaptation_gate_result is None:
        reasons.append(
            HandoffReason(
                code="adaptation-gate-missing",
                severity=HandoffReasonSeverity.WARNING,
                message="No adaptation-gate result was attached to the handoff package.",
                source="adaptation",
            )
        )
    else:
        reasons.append(_adaptation_reason(adaptation_gate_result))

    if reality_delta_report is None:
        reasons.append(
            HandoffReason(
                code="reality-delta-missing",
                severity=HandoffReasonSeverity.WARNING,
                message="No reality-delta report was attached to the handoff package.",
                source="reality-delta",
            )
        )
    else:
        reasons.append(_reality_delta_reason(reality_delta_report))

    if model_confidence_profile is None:
        reasons.append(
            HandoffReason(
                code="model-confidence-missing",
                severity=HandoffReasonSeverity.WARNING,
                message="No model-confidence profile was attached to the handoff package.",
                source="model-confidence",
            )
        )
    else:
        reasons.append(
            HandoffReason(
                code=f"model-confidence-{model_confidence_profile.trust_tier.value}",
                severity=HandoffReasonSeverity.INFO
                if model_confidence_profile.allows_adaptation_review
                else HandoffReasonSeverity.ERROR,
                message=(
                    f"Model-confidence profile tier is {model_confidence_profile.trust_tier.value}."
                ),
                source=f"model-confidence:{model_confidence_profile.profile_id}",
            )
        )

    return _normalize_handoff_reasons(tuple(reasons))


def _build_handoff_artifacts(
    *,
    prediction: PredictionResult,
    receipt: PredictionReceipt,
    receipt_chain: ReceiptChain,
    receipt_chain_validation: ReceiptChainValidationResult,
    policy_evaluation: PolicyEvaluation | None,
    adaptation_gate_result: AdaptationGateResult | None,
    reality_delta_report: RealityDeltaReport | None,
    model_confidence_profile: ModelConfidenceProfile | None,
) -> tuple[HandoffArtifact, ...]:
    artifacts = [
        HandoffArtifact(
            artifact_id=prediction.prediction_id,
            artifact_type="prediction-result",
            fingerprint=prediction.fingerprint(),
            source="prediction",
        ),
        HandoffArtifact(
            artifact_id=receipt.receipt_id,
            artifact_type="prediction-receipt",
            fingerprint=receipt.fingerprint(),
            source="receipt",
        ),
        HandoffArtifact(
            artifact_id=receipt_chain.chain_id,
            artifact_type="receipt-chain",
            fingerprint=receipt_chain.fingerprint(),
            source="receipt-chain",
        ),
        HandoffArtifact(
            artifact_id=f"{receipt_chain_validation.chain_id}:validation",
            artifact_type="receipt-chain-validation",
            fingerprint=receipt_chain_validation.fingerprint(),
            source="receipt-chain",
        ),
    ]

    if policy_evaluation is not None:
        artifacts.append(
            HandoffArtifact(
                artifact_id=policy_evaluation.policy_evaluation_id,
                artifact_type="policy-evaluation",
                fingerprint=policy_evaluation.fingerprint(),
                source="policy",
            )
        )
    if adaptation_gate_result is not None:
        artifacts.append(
            HandoffArtifact(
                artifact_id=adaptation_gate_result.gate_result_id,
                artifact_type="adaptation-gate-result",
                fingerprint=adaptation_gate_result.fingerprint(),
                source="adaptation",
            )
        )
    if reality_delta_report is not None:
        artifacts.append(
            HandoffArtifact(
                artifact_id=reality_delta_report.report_id,
                artifact_type="reality-delta-report",
                fingerprint=reality_delta_report.fingerprint(),
                source="reality-delta",
            )
        )
    if model_confidence_profile is not None:
        artifacts.append(
            HandoffArtifact(
                artifact_id=model_confidence_profile.profile_id,
                artifact_type="model-confidence-profile",
                fingerprint=model_confidence_profile.fingerprint(),
                source="model-confidence",
            )
        )

    return _normalize_handoff_artifacts(tuple(artifacts))


def _prediction_reason(prediction: PredictionResult) -> HandoffReason:
    if prediction.disposition is PredictionDisposition.ACCEPT:
        severity = HandoffReasonSeverity.INFO
    elif prediction.disposition in {
        PredictionDisposition.REVIEW,
        PredictionDisposition.CAUTION,
    }:
        severity = HandoffReasonSeverity.WARNING
    elif prediction.disposition is PredictionDisposition.DENY:
        severity = HandoffReasonSeverity.ERROR
    else:
        severity = HandoffReasonSeverity.CRITICAL

    return HandoffReason(
        code=f"prediction-{prediction.disposition.value}",
        severity=severity,
        message=f"Prediction disposition is {prediction.disposition.value}.",
        source=f"prediction:{prediction.prediction_id}",
    )


def _receipt_reason(receipt: PredictionReceipt) -> HandoffReason:
    if receipt.review_decision is ReceiptReviewDecision.RECORD_ONLY:
        severity = HandoffReasonSeverity.INFO
    elif receipt.review_decision is ReceiptReviewDecision.HUMAN_REVIEW_REQUIRED:
        severity = HandoffReasonSeverity.WARNING
    else:
        severity = HandoffReasonSeverity.ERROR

    return HandoffReason(
        code=f"receipt-{receipt.review_decision.value}",
        severity=severity,
        message=f"Receipt review decision is {receipt.review_decision.value}.",
        source=f"receipt:{receipt.receipt_id}",
    )


def _receipt_chain_reason(validation: ReceiptChainValidationResult) -> HandoffReason:
    if validation.status is ReceiptChainValidationStatus.PASS:
        return HandoffReason(
            code="receipt-chain-valid",
            severity=HandoffReasonSeverity.INFO,
            message="Receipt-chain validation passed.",
            source=f"receipt-chain:{validation.chain_id}",
        )

    return HandoffReason(
        code="receipt-chain-invalid",
        severity=HandoffReasonSeverity.ERROR,
        message="Receipt-chain validation failed.",
        source=f"receipt-chain:{validation.chain_id}",
    )


def _policy_reason(policy: PolicyEvaluation) -> HandoffReason:
    if policy.decision is PolicyDecision.ALLOW:
        severity = HandoffReasonSeverity.INFO
    elif policy.decision is PolicyDecision.CAUTION:
        severity = HandoffReasonSeverity.WARNING
    elif policy.decision is PolicyDecision.DENY:
        severity = HandoffReasonSeverity.ERROR
    else:
        severity = HandoffReasonSeverity.CRITICAL

    return HandoffReason(
        code=f"policy-{policy.decision.value}",
        severity=severity,
        message=f"Policy evaluation decision is {policy.decision.value}.",
        source=f"policy:{policy.policy_evaluation_id}",
    )


def _adaptation_reason(result: AdaptationGateResult) -> HandoffReason:
    if result.decision is AdaptationDecision.READY_FOR_HUMAN_REVIEW:
        severity = HandoffReasonSeverity.INFO
    elif result.decision is AdaptationDecision.CAUTION_REVIEW:
        severity = HandoffReasonSeverity.WARNING
    elif result.decision is AdaptationDecision.DENY:
        severity = HandoffReasonSeverity.ERROR
    else:
        severity = HandoffReasonSeverity.CRITICAL

    return HandoffReason(
        code=f"adaptation-{result.decision.value}",
        severity=severity,
        message=f"Adaptation-gate decision is {result.decision.value}.",
        source=f"adaptation:{result.gate_result_id}",
    )


def _reality_delta_reason(report: RealityDeltaReport) -> HandoffReason:
    if report.verdict is RealityDeltaVerdict.MATCH:
        severity = HandoffReasonSeverity.INFO
    elif report.verdict is RealityDeltaVerdict.DRIFT:
        severity = HandoffReasonSeverity.WARNING
    elif report.verdict is RealityDeltaVerdict.BREACH:
        severity = HandoffReasonSeverity.ERROR
    else:
        severity = HandoffReasonSeverity.CRITICAL

    return HandoffReason(
        code=f"reality-delta-{report.verdict.value}",
        severity=severity,
        message=f"Reality-delta verdict is {report.verdict.value}.",
        source=f"reality-delta:{report.report_id}",
    )


def _normalize_handoff_reasons(reasons: tuple[HandoffReason, ...]) -> tuple[HandoffReason, ...]:
    if not reasons:
        raise ValueError("handoff package requires at least one reason")

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


def _normalize_handoff_artifacts(
    artifacts: tuple[HandoffArtifact, ...],
) -> tuple[HandoffArtifact, ...]:
    if not artifacts:
        raise ValueError("handoff package requires at least one artifact")

    seen_ids: set[str] = set()
    normalized: list[HandoffArtifact] = []

    for artifact in artifacts:
        if artifact.artifact_id in seen_ids:
            raise ValueError(f"duplicate handoff artifact id: {artifact.artifact_id}")
        seen_ids.add(artifact.artifact_id)
        normalized.append(artifact)

    return tuple(sorted(normalized, key=lambda item: item.artifact_id))


def _severity_rank(severity: HandoffReasonSeverity) -> int:
    ranks = {
        HandoffReasonSeverity.INFO: 0,
        HandoffReasonSeverity.WARNING: 1,
        HandoffReasonSeverity.ERROR: 2,
        HandoffReasonSeverity.CRITICAL: 3,
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

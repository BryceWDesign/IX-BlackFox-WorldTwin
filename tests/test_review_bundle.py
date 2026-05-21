from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _ready_handoff() -> worldtwin.HandoffPackage:
    reason = worldtwin.HandoffReason(
        code="human-authority-required",
        severity=worldtwin.HandoffReasonSeverity.INFO,
        message="Handoff package is review-only and requires human authority.",
        source="prediction:prediction-alpha",
    )
    artifact = worldtwin.HandoffArtifact(
        artifact_id="prediction-alpha",
        artifact_type="prediction-result",
        fingerprint="fingerprint-alpha",
        source="prediction",
    )

    return worldtwin.HandoffPackage(
        handoff_id="handoff-alpha",
        target=worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE,
        decision=worldtwin.HandoffDecision.READY_FOR_REVIEW,
        scenario_id="scenario-alpha",
        prediction_id="prediction-alpha",
        receipt_id="prediction-receipt-alpha",
        receipt_chain_id="receipt-chain-alpha",
        created_at=_created_at(),
        created_by="worldtwin-handoff-gate",
        requested_action="Queue evidence package for human execution-governance review.",
        reasons=(reason,),
        artifacts=(artifact,),
    )


def _caution_handoff() -> worldtwin.HandoffPackage:
    reason = worldtwin.HandoffReason(
        code="policy-evaluation-missing",
        severity=worldtwin.HandoffReasonSeverity.WARNING,
        message="No policy evaluation was attached to the handoff package.",
        source="policy",
    )
    artifact = worldtwin.HandoffArtifact(
        artifact_id="prediction-alpha",
        artifact_type="prediction-result",
        fingerprint="fingerprint-alpha",
        source="prediction",
    )

    return worldtwin.HandoffPackage(
        handoff_id="handoff-caution",
        target=worldtwin.HandoffTarget.HUMAN_REVIEW_QUEUE,
        decision=worldtwin.HandoffDecision.CAUTION_REVIEW,
        scenario_id="scenario-alpha",
        prediction_id="prediction-alpha",
        receipt_id="prediction-receipt-alpha",
        receipt_chain_id="receipt-chain-alpha",
        created_at=_created_at(),
        created_by="worldtwin-handoff-gate",
        requested_action="Queue evidence package for cautious human review.",
        reasons=(reason,),
        artifacts=(artifact,),
    )


def test_review_bundle_exports_handoff_without_execution_authority() -> None:
    handoff = _ready_handoff()
    bundle = worldtwin.create_review_bundle(
        handoff=handoff,
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )

    assert bundle.bundle_id.startswith("review-bundle-")
    assert bundle.schema_version == worldtwin.REVIEW_BUNDLE_SCHEMA_VERSION
    assert bundle.export_format is worldtwin.ReviewBundleFormat.CANONICAL_JSON
    assert bundle.handoff_id == handoff.handoff_id
    assert bundle.target is worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE
    assert bundle.decision is worldtwin.HandoffDecision.READY_FOR_REVIEW
    assert bundle.handoff_fingerprint == handoff.fingerprint()
    assert bundle.reason_codes == handoff.reason_codes()
    assert bundle.artifact_ids == ("prediction-alpha",)
    assert bundle.requires_human_authority is True
    assert bundle.allowed_for_automatic_execution is False
    assert bundle.may_enter_human_review is True
    assert bundle.blocks_downstream_review is False


def test_review_bundle_contains_canonical_handoff_payload_json() -> None:
    handoff = _ready_handoff()
    bundle = worldtwin.create_review_bundle(
        handoff=handoff,
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )
    decoded_handoff_payload = json.loads(bundle.handoff_payload_json)
    decoded_bundle_payload = json.loads(bundle.to_json())

    assert decoded_handoff_payload == handoff.canonical_payload()
    assert decoded_bundle_payload["bundle_id"] == bundle.bundle_id
    assert decoded_bundle_payload["handoff_payload_json"] == bundle.handoff_payload_json
    assert decoded_bundle_payload["allowed_for_automatic_execution"] is False
    assert decoded_bundle_payload["requires_human_authority"] is True


def test_review_bundle_validation_passes_for_clean_bundle() -> None:
    bundle = worldtwin.create_review_bundle(
        handoff=_ready_handoff(),
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )

    validation = worldtwin.validate_review_bundle(
        bundle=bundle,
        checked_at=_created_at(),
        checked_by="worldtwin-review-bundle-gate",
    )

    assert validation.validation_id.startswith("review-bundle-validation-")
    assert validation.status is worldtwin.ReviewBundleValidationStatus.PASS
    assert validation.passed is True
    assert validation.issues == ()
    assert validation.bundle_id == bundle.bundle_id


def test_review_bundle_preserves_caution_decision() -> None:
    handoff = _caution_handoff()
    bundle = worldtwin.create_review_bundle(
        handoff=handoff,
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )

    assert bundle.decision is worldtwin.HandoffDecision.CAUTION_REVIEW
    assert bundle.may_enter_human_review is True
    assert bundle.blocks_downstream_review is False
    assert bundle.reason_codes == ("policy-evaluation-missing",)


def test_review_bundle_fingerprint_is_replay_stable() -> None:
    first = worldtwin.create_review_bundle(
        handoff=_ready_handoff(),
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )
    second = worldtwin.create_review_bundle(
        handoff=_ready_handoff(),
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )

    assert first.bundle_id == second.bundle_id
    assert first.fingerprint() == second.fingerprint()
    assert first.to_json() == second.to_json()


def test_review_bundle_rejects_tampered_handoff_payload() -> None:
    handoff = _ready_handoff()
    bundle = worldtwin.create_review_bundle(
        handoff=handoff,
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )
    tampered_payload = bundle.handoff_payload()
    tampered_payload["decision"] = worldtwin.HandoffDecision.BLOCKED.value

    with pytest.raises(
        ValueError,
        match="review bundle handoff fingerprint does not match payload",
    ):
        worldtwin.ReviewBundle(
            bundle_id="review-bundle-manual",
            handoff_id=bundle.handoff_id,
            target=bundle.target,
            decision=bundle.decision,
            created_at=bundle.created_at,
            created_by=bundle.created_by,
            requested_action=bundle.requested_action,
            handoff_fingerprint=bundle.handoff_fingerprint,
            handoff_payload_json=json.dumps(tampered_payload),
            reason_codes=bundle.reason_codes,
            artifact_ids=bundle.artifact_ids,
        )


def test_review_bundle_rejects_automatic_execution_flag_when_constructed_directly() -> None:
    bundle = worldtwin.create_review_bundle(
        handoff=_ready_handoff(),
        created_at=_created_at(),
        created_by="worldtwin-review-bundle-gate",
    )

    with pytest.raises(ValueError, match="review bundle must never allow automatic execution"):
        worldtwin.ReviewBundle(
            bundle_id="review-bundle-manual",
            handoff_id=bundle.handoff_id,
            target=bundle.target,
            decision=bundle.decision,
            created_at=bundle.created_at,
            created_by=bundle.created_by,
            requested_action=bundle.requested_action,
            handoff_fingerprint=bundle.handoff_fingerprint,
            handoff_payload_json=bundle.handoff_payload_json,
            reason_codes=bundle.reason_codes,
            artifact_ids=bundle.artifact_ids,
            allowed_for_automatic_execution=True,
        )


def test_review_bundle_validation_result_rejects_status_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="review-bundle validation status must match issue state",
    ):
        worldtwin.ReviewBundleValidationResult(
            validation_id="review-bundle-validation-manual",
            bundle_id="review-bundle-alpha",
            status=worldtwin.ReviewBundleValidationStatus.PASS,
            checked_at=_created_at(),
            checked_by="worldtwin-review-bundle-gate",
            issues=("issue-alpha",),
        )

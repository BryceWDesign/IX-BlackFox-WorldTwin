from __future__ import annotations

import json

import pytest

import ix_blackfox_worldtwin as worldtwin
from ix_blackfox_worldtwin import cli


def test_wave1_acceptance_builds_complete_human_review_bundle() -> None:
    bundle = cli.build_demo_review_bundle()
    validation = worldtwin.validate_review_bundle(
        bundle=bundle,
        checked_at=cli.DEMO_CREATED_AT,
        checked_by="worldtwin-wave1-acceptance",
    )

    assert bundle.schema_version == worldtwin.REVIEW_BUNDLE_SCHEMA_VERSION
    assert bundle.target is worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE
    assert bundle.decision is worldtwin.HandoffDecision.READY_FOR_REVIEW
    assert bundle.requires_human_authority is True
    assert bundle.allowed_for_automatic_execution is False
    assert bundle.may_enter_human_review is True
    assert bundle.blocks_downstream_review is False
    assert validation.passed is True
    assert validation.issues == ()


def test_wave1_acceptance_export_is_replay_stable_and_canonical_json() -> None:
    first = cli.build_demo_review_bundle()
    second = cli.build_demo_review_bundle()

    first_payload = json.loads(first.to_json())
    second_payload = json.loads(second.to_json())

    assert first.bundle_id == second.bundle_id
    assert first.fingerprint() == second.fingerprint()
    assert first.to_json() == second.to_json()
    assert first_payload == second_payload
    assert first_payload["schema_version"] == worldtwin.REVIEW_BUNDLE_SCHEMA_VERSION
    assert first_payload["export_format"] == worldtwin.ReviewBundleFormat.CANONICAL_JSON.value
    assert first_payload["requires_human_authority"] is True
    assert first_payload["allowed_for_automatic_execution"] is False
    assert first_payload["reason_codes"] == sorted(first_payload["reason_codes"])
    assert first_payload["artifact_ids"] == sorted(first_payload["artifact_ids"])


def test_wave1_acceptance_handoff_payload_preserves_full_evidence_chain() -> None:
    bundle = cli.build_demo_review_bundle()
    handoff_payload = bundle.handoff_payload()

    artifact_types = {artifact["artifact_type"] for artifact in handoff_payload["artifacts"]}
    reason_codes = set(
        handoff_payload["reasons"][index]["code"]
        for index in range(len(handoff_payload["reasons"]))
    )

    assert artifact_types == {
        "adaptation-gate-result",
        "model-confidence-profile",
        "policy-evaluation",
        "prediction-receipt",
        "prediction-result",
        "receipt-chain",
        "receipt-chain-validation",
        "reality-delta-report",
    }
    assert {
        "adaptation-ready-for-human-review",
        "human-authority-required",
        "model-confidence-trusted",
        "policy-allow",
        "prediction-accept",
        "reality-delta-match",
        "receipt-chain-valid",
        "receipt-record-only",
    }.issubset(reason_codes)
    assert handoff_payload["requires_human_authority"] is True
    assert handoff_payload["allowed_for_automatic_execution"] is False


def test_wave1_acceptance_public_api_exposes_core_contracts() -> None:
    expected_exports = {
        "AdaptationGateResult",
        "AssumptionLedger",
        "BranchComparison",
        "ConfidenceAssessment",
        "ConstraintSet",
        "EvidenceReference",
        "HandoffPackage",
        "ModelConfidenceProfile",
        "PredictionReceipt",
        "PredictionResult",
        "RealityDeltaReport",
        "ReceiptChain",
        "ReviewBundle",
        "RiskProfile",
        "ScenarioManifest",
        "SimulationResult",
        "WorldState",
        "build_thermal_drift_scenario",
        "create_handoff_package",
        "create_prediction_receipt",
        "create_reality_delta_report",
        "create_review_bundle",
        "evaluate_adaptation_gate",
        "run_branching_simulation",
        "run_deterministic_simulation",
        "validate_review_bundle",
    }

    missing_exports = sorted(name for name in expected_exports if not hasattr(worldtwin, name))

    assert missing_exports == []


def test_wave1_acceptance_cli_demo_matches_programmatic_bundle(
    capsys: pytest.CaptureFixture[str],
) -> None:
    programmatic_bundle = cli.build_demo_review_bundle()

    exit_code = cli.main(["run-demo"])
    captured = capsys.readouterr()
    cli_payload = json.loads(captured.out)
    programmatic_payload = json.loads(programmatic_bundle.to_json())

    assert exit_code == 0
    assert cli_payload == programmatic_payload
    assert cli_payload["bundle_id"] == programmatic_bundle.bundle_id
    assert cli_payload["handoff_fingerprint"] == programmatic_bundle.handoff_fingerprint
    assert cli_payload["requires_human_authority"] is True
    assert cli_payload["allowed_for_automatic_execution"] is False


def test_wave1_acceptance_claim_boundary_posture_is_conservative() -> None:
    assert len(worldtwin.GITHUB_DESCRIPTION) <= worldtwin.GITHUB_DESCRIPTION_LIMIT
    assert worldtwin.get_external_description_issues(worldtwin.GITHUB_DESCRIPTION) == ()
    assert worldtwin.is_prohibited_claim("IX-BlackFox-WorldTwin is certified AGI.") is True
    assert worldtwin.is_prohibited_claim("IX-BlackFox-WorldTwin is production approved.") is True
    assert (
        worldtwin.is_claim_language_allowed(
            "WorldTwin packages scenario evidence for human review before execution."
        )
        is True
    )
    assert (
        worldtwin.is_claim_language_allowed(
            "WorldTwin is certified autonomous AGI for operational deployment."
        )
        is False
    )


def test_wave1_acceptance_no_automatic_authority_appears_in_exported_bundle() -> None:
    bundle = cli.build_demo_review_bundle()
    payload = json.loads(bundle.to_json())
    handoff_payload = json.loads(payload["handoff_payload_json"])

    assert payload["requires_human_authority"] is True
    assert payload["allowed_for_automatic_execution"] is False
    assert handoff_payload["requires_human_authority"] is True
    assert handoff_payload["allowed_for_automatic_execution"] is False
    assert handoff_payload["decision"] == worldtwin.HandoffDecision.READY_FOR_REVIEW.value
    assert payload["decision"] == worldtwin.HandoffDecision.READY_FOR_REVIEW.value


def test_wave1_acceptance_metadata_stays_source_available_not_open_source() -> None:
    identity = worldtwin.get_package_identity()

    assert identity.project_name == worldtwin.PROJECT_NAME
    assert identity.package_name == worldtwin.PACKAGE_NAME
    assert identity.license_name == worldtwin.LICENSE_NAME
    assert "source-available" in worldtwin.PUBLIC_DESCRIPTION.lower()
    assert "open source" not in worldtwin.PUBLIC_DESCRIPTION.lower()
    assert "open-source" not in worldtwin.PUBLIC_DESCRIPTION.lower()

from __future__ import annotations

import json

import ix_blackfox_worldtwin as worldtwin
from ix_blackfox_worldtwin import cli


def test_build_demo_review_bundle_returns_valid_human_review_bundle() -> None:
    bundle = cli.build_demo_review_bundle()

    assert bundle.bundle_id.startswith("review-bundle-")
    assert bundle.schema_version == worldtwin.REVIEW_BUNDLE_SCHEMA_VERSION
    assert bundle.target is worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE
    assert bundle.decision is worldtwin.HandoffDecision.READY_FOR_REVIEW
    assert bundle.requires_human_authority is True
    assert bundle.allowed_for_automatic_execution is False
    assert bundle.may_enter_human_review is True
    assert bundle.blocks_downstream_review is False
    assert "human-authority-required" in bundle.reason_codes
    assert "receipt-chain-valid" in bundle.reason_codes
    assert "reality-delta-match" in bundle.reason_codes
    assert "adaptation-ready-for-human-review" in bundle.reason_codes


def test_cli_run_demo_emits_canonical_json(capsys) -> None:
    exit_code = cli.main(["run-demo"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema_version"] == worldtwin.REVIEW_BUNDLE_SCHEMA_VERSION
    assert payload["target"] == worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE.value
    assert payload["decision"] == worldtwin.HandoffDecision.READY_FOR_REVIEW.value
    assert payload["requires_human_authority"] is True
    assert payload["allowed_for_automatic_execution"] is False
    assert payload["export_format"] == worldtwin.ReviewBundleFormat.CANONICAL_JSON.value
    assert payload["bundle_id"].startswith("review-bundle-")
    assert payload["handoff_id"].startswith("handoff-")
    assert payload["reason_codes"] == sorted(payload["reason_codes"])
    assert payload["artifact_ids"] == sorted(payload["artifact_ids"])


def test_cli_run_demo_pretty_prints_valid_json(capsys) -> None:
    exit_code = cli.main(["run-demo", "--pretty"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert "\n  " in captured.out
    assert payload["schema_version"] == worldtwin.REVIEW_BUNDLE_SCHEMA_VERSION
    assert payload["requires_human_authority"] is True
    assert payload["allowed_for_automatic_execution"] is False


def test_demo_review_bundle_is_replay_stable() -> None:
    first = cli.build_demo_review_bundle()
    second = cli.build_demo_review_bundle()

    assert first.bundle_id == second.bundle_id
    assert first.fingerprint() == second.fingerprint()
    assert first.to_json() == second.to_json()


def test_demo_review_bundle_validation_passes() -> None:
    bundle = cli.build_demo_review_bundle()
    validation = worldtwin.validate_review_bundle(
        bundle=bundle,
        checked_at=cli.DEMO_CREATED_AT,
        checked_by="worldtwin-cli-test",
    )

    assert validation.status is worldtwin.ReviewBundleValidationStatus.PASS
    assert validation.passed is True
    assert validation.issues == ()

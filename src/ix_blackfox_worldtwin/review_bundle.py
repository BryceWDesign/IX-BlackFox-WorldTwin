"""BlackFox-facing review bundle export for IX-BlackFox-WorldTwin.

A review bundle is the deterministic export wrapper around a WorldTwin handoff
package. It is designed for downstream governance systems to verify, archive,
or queue for human review. It is not an execution token and it never grants
automatic authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.handoff import HandoffDecision, HandoffPackage, HandoffTarget

REVIEW_BUNDLE_SCHEMA_VERSION = "blackfox-review-bundle-v1"
REVIEW_BUNDLE_ID_DIGEST_LENGTH = 16


class ReviewBundleFormat(StrEnum):
    """Supported review-bundle export formats."""

    CANONICAL_JSON = "canonical-json"


class ReviewBundleValidationStatus(StrEnum):
    """Validation status for a review bundle."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ReviewBundle:
    """A deterministic, human-review-only export bundle for a handoff package."""

    bundle_id: str
    handoff_id: str
    target: HandoffTarget
    decision: HandoffDecision
    created_at: datetime
    created_by: str
    requested_action: str
    handoff_fingerprint: str
    handoff_payload_json: str
    reason_codes: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    export_format: ReviewBundleFormat = ReviewBundleFormat.CANONICAL_JSON
    requires_human_authority: bool = True
    allowed_for_automatic_execution: bool = False
    schema_version: str = REVIEW_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a review bundle."""

        if not self.requires_human_authority:
            raise ValueError("review bundle must require human authority")
        if self.allowed_for_automatic_execution:
            raise ValueError("review bundle must never allow automatic execution")

        payload = _decode_json_object(self.handoff_payload_json, "handoff payload json")
        normalized_handoff_payload_json = _canonical_json(payload)
        expected_handoff_fingerprint = _stable_sha256(payload)
        normalized_reason_codes = _normalize_unique_text_tuple(
            self.reason_codes,
            "reason code",
        )
        normalized_artifact_ids = _normalize_unique_text_tuple(
            self.artifact_ids,
            "artifact id",
        )

        if expected_handoff_fingerprint != self.handoff_fingerprint:
            raise ValueError("review bundle handoff fingerprint does not match payload")
        if payload.get("handoff_id") != self.handoff_id:
            raise ValueError("review bundle handoff_id must match handoff payload")
        if payload.get("target") != self.target.value:
            raise ValueError("review bundle target must match handoff payload")
        if payload.get("decision") != self.decision.value:
            raise ValueError("review bundle decision must match handoff payload")
        if payload.get("requested_action") != self.requested_action:
            raise ValueError("review bundle requested_action must match handoff payload")
        if payload.get("requires_human_authority") is not True:
            raise ValueError("review bundle payload must require human authority")
        if payload.get("allowed_for_automatic_execution") is not False:
            raise ValueError("review bundle payload must not allow automatic execution")

        payload_reason_codes = _reason_codes_from_handoff_payload(payload)
        payload_artifact_ids = _artifact_ids_from_handoff_payload(payload)

        if payload_reason_codes != normalized_reason_codes:
            raise ValueError("review bundle reason_codes must match handoff payload")
        if payload_artifact_ids != normalized_artifact_ids:
            raise ValueError("review bundle artifact_ids must match handoff payload")

        object.__setattr__(self, "bundle_id", _require_non_empty(self.bundle_id, "bundle id"))
        object.__setattr__(self, "handoff_id", _require_non_empty(self.handoff_id, "handoff id"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "review bundle created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "requested_action",
            _require_non_empty(self.requested_action, "requested action"),
        )
        object.__setattr__(
            self,
            "handoff_fingerprint",
            _require_non_empty(self.handoff_fingerprint, "handoff fingerprint"),
        )
        object.__setattr__(self, "handoff_payload_json", normalized_handoff_payload_json)
        object.__setattr__(self, "reason_codes", normalized_reason_codes)
        object.__setattr__(self, "artifact_ids", normalized_artifact_ids)
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "review bundle schema version"),
        )

    @property
    def may_enter_human_review(self) -> bool:
        """Return True when the bundle may enter human review."""

        return self.decision in {
            HandoffDecision.READY_FOR_REVIEW,
            HandoffDecision.CAUTION_REVIEW,
        }

    @property
    def blocks_downstream_review(self) -> bool:
        """Return True when the bundle blocks downstream review."""

        return self.decision in {
            HandoffDecision.BLOCKED,
            HandoffDecision.QUARANTINED,
        }

    def handoff_payload(self) -> dict[str, Any]:
        """Return the decoded handoff payload."""

        return _decode_json_object(self.handoff_payload_json, "handoff payload json")

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for export hashing."""

        return {
            "allowed_for_automatic_execution": self.allowed_for_automatic_execution,
            "artifact_ids": list(self.artifact_ids),
            "bundle_id": self.bundle_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "decision": self.decision.value,
            "export_format": self.export_format.value,
            "handoff_fingerprint": self.handoff_fingerprint,
            "handoff_id": self.handoff_id,
            "handoff_payload_json": self.handoff_payload_json,
            "reason_codes": list(self.reason_codes),
            "requested_action": self.requested_action,
            "requires_human_authority": self.requires_human_authority,
            "schema_version": self.schema_version,
            "target": self.target.value,
        }

    def to_json(self) -> str:
        """Return the canonical JSON export representation."""

        return _canonical_json(self.canonical_payload())

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this review bundle."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ReviewBundleValidationResult:
    """Result of validating a review bundle."""

    validation_id: str
    bundle_id: str
    status: ReviewBundleValidationStatus
    checked_at: datetime
    checked_by: str
    issues: tuple[str, ...] = ()
    schema_version: str = REVIEW_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a review-bundle validation result."""

        expected_status = (
            ReviewBundleValidationStatus.PASS
            if not self.issues
            else ReviewBundleValidationStatus.FAIL
        )
        if self.status is not expected_status:
            raise ValueError("review-bundle validation status must match issue state")

        object.__setattr__(
            self,
            "validation_id",
            _require_non_empty(self.validation_id, "validation id"),
        )
        object.__setattr__(self, "bundle_id", _require_non_empty(self.bundle_id, "bundle id"))
        object.__setattr__(
            self,
            "checked_at",
            _require_aware_utc_datetime(self.checked_at, "validation checked_at"),
        )
        object.__setattr__(self, "checked_by", _require_non_empty(self.checked_by, "checked by"))
        object.__setattr__(
            self,
            "issues",
            _normalize_unique_text_tuple(self.issues, "validation issue"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "review bundle schema version"),
        )

    @property
    def passed(self) -> bool:
        """Return True when validation passed."""

        return self.status is ReviewBundleValidationStatus.PASS

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for validation hashing."""

        return {
            "bundle_id": self.bundle_id,
            "checked_at": self.checked_at.isoformat(),
            "checked_by": self.checked_by,
            "issues": list(self.issues),
            "schema_version": self.schema_version,
            "status": self.status.value,
            "validation_id": self.validation_id,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this validation result."""

        return _stable_sha256(self.canonical_payload())


def create_review_bundle(
    *,
    handoff: HandoffPackage,
    created_at: datetime,
    created_by: str,
    bundle_id: str | None = None,
) -> ReviewBundle:
    """Create a deterministic review bundle from a handoff package."""

    normalized_created_at = _require_aware_utc_datetime(
        created_at,
        "review bundle created_at",
    )
    normalized_created_by = _require_non_empty(created_by, "created by")
    handoff_payload = handoff.canonical_payload()
    handoff_payload_json = _canonical_json(handoff_payload)
    handoff_fingerprint = handoff.fingerprint()
    reason_codes = handoff.reason_codes()
    artifact_ids = tuple(sorted(handoff.artifact_table()))
    resolved_bundle_id = bundle_id or make_review_bundle_id(
        handoff_id=handoff.handoff_id,
        target=handoff.target,
        decision=handoff.decision,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        requested_action=handoff.requested_action,
        handoff_fingerprint=handoff_fingerprint,
        handoff_payload_json=handoff_payload_json,
        reason_codes=reason_codes,
        artifact_ids=artifact_ids,
    )

    return ReviewBundle(
        bundle_id=resolved_bundle_id,
        handoff_id=handoff.handoff_id,
        target=handoff.target,
        decision=handoff.decision,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        requested_action=handoff.requested_action,
        handoff_fingerprint=handoff_fingerprint,
        handoff_payload_json=handoff_payload_json,
        reason_codes=reason_codes,
        artifact_ids=artifact_ids,
    )


def validate_review_bundle(
    *,
    bundle: ReviewBundle,
    checked_at: datetime,
    checked_by: str,
    validation_id: str | None = None,
) -> ReviewBundleValidationResult:
    """Validate that a review bundle is internally consistent."""

    issues: list[str] = []
    payload = bundle.handoff_payload()

    if _stable_sha256(payload) != bundle.handoff_fingerprint:
        issues.append("handoff payload fingerprint mismatch")
    if payload.get("handoff_id") != bundle.handoff_id:
        issues.append("handoff id mismatch")
    if payload.get("target") != bundle.target.value:
        issues.append("target mismatch")
    if payload.get("decision") != bundle.decision.value:
        issues.append("decision mismatch")
    if payload.get("requires_human_authority") is not True:
        issues.append("human authority requirement missing")
    if payload.get("allowed_for_automatic_execution") is not False:
        issues.append("automatic execution flag is not false")
    if _reason_codes_from_handoff_payload(payload) != bundle.reason_codes:
        issues.append("reason code mismatch")
    if _artifact_ids_from_handoff_payload(payload) != bundle.artifact_ids:
        issues.append("artifact id mismatch")

    status = ReviewBundleValidationStatus.PASS if not issues else ReviewBundleValidationStatus.FAIL
    normalized_checked_at = _require_aware_utc_datetime(
        checked_at,
        "validation checked_at",
    )
    normalized_checked_by = _require_non_empty(checked_by, "checked by")
    normalized_issues = _normalize_unique_text_tuple(tuple(issues), "validation issue")
    resolved_validation_id = validation_id or make_review_bundle_validation_id(
        bundle_id=bundle.bundle_id,
        status=status,
        checked_at=normalized_checked_at,
        checked_by=normalized_checked_by,
        issues=normalized_issues,
    )

    return ReviewBundleValidationResult(
        validation_id=resolved_validation_id,
        bundle_id=bundle.bundle_id,
        status=status,
        checked_at=normalized_checked_at,
        checked_by=normalized_checked_by,
        issues=normalized_issues,
    )


def make_review_bundle_id(
    *,
    handoff_id: str,
    target: HandoffTarget,
    decision: HandoffDecision,
    created_at: datetime,
    created_by: str,
    requested_action: str,
    handoff_fingerprint: str,
    handoff_payload_json: str,
    reason_codes: tuple[str, ...],
    artifact_ids: tuple[str, ...],
) -> str:
    """Create a deterministic review-bundle id."""

    payload = {
        "allowed_for_automatic_execution": False,
        "artifact_ids": list(_normalize_unique_text_tuple(artifact_ids, "artifact id")),
        "created_at": _require_aware_utc_datetime(
            created_at,
            "review bundle created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "decision": decision.value,
        "export_format": ReviewBundleFormat.CANONICAL_JSON.value,
        "handoff_fingerprint": _require_non_empty(handoff_fingerprint, "handoff fingerprint"),
        "handoff_id": _require_non_empty(handoff_id, "handoff id"),
        "handoff_payload_json": _canonical_json(
            _decode_json_object(handoff_payload_json, "handoff payload json")
        ),
        "reason_codes": list(_normalize_unique_text_tuple(reason_codes, "reason code")),
        "requested_action": _require_non_empty(requested_action, "requested action"),
        "requires_human_authority": True,
        "schema_version": REVIEW_BUNDLE_SCHEMA_VERSION,
        "target": target.value,
    }
    digest = _stable_sha256(payload)[:REVIEW_BUNDLE_ID_DIGEST_LENGTH]
    return f"review-bundle-{digest}"


def make_review_bundle_validation_id(
    *,
    bundle_id: str,
    status: ReviewBundleValidationStatus,
    checked_at: datetime,
    checked_by: str,
    issues: tuple[str, ...] = (),
) -> str:
    """Create a deterministic review-bundle validation id."""

    payload = {
        "bundle_id": _require_non_empty(bundle_id, "bundle id"),
        "checked_at": _require_aware_utc_datetime(
            checked_at,
            "validation checked_at",
        ).isoformat(),
        "checked_by": _require_non_empty(checked_by, "checked by"),
        "issues": list(_normalize_unique_text_tuple(issues, "validation issue")),
        "schema_version": REVIEW_BUNDLE_SCHEMA_VERSION,
        "status": status.value,
    }
    digest = _stable_sha256(payload)[:REVIEW_BUNDLE_ID_DIGEST_LENGTH]
    return f"review-bundle-validation-{digest}"


def _reason_codes_from_handoff_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    reasons = payload.get("reasons")
    if not isinstance(reasons, list):
        raise ValueError("handoff payload reasons must be a list")

    reason_codes: list[str] = []
    for reason in reasons:
        if not isinstance(reason, dict):
            raise ValueError("handoff payload reason must be an object")
        reason_codes.append(_require_non_empty(str(reason.get("code", "")), "reason code"))

    return _normalize_unique_text_tuple(tuple(reason_codes), "reason code")


def _artifact_ids_from_handoff_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("handoff payload artifacts must be a list")

    artifact_ids: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("handoff payload artifact must be an object")
        artifact_ids.append(
            _require_non_empty(str(artifact.get("artifact_id", "")), "artifact id")
        )

    return _normalize_unique_text_tuple(tuple(artifact_ids), "artifact id")


def _decode_json_object(value: str, field_name: str) -> dict[str, Any]:
    text = _require_non_empty(value, field_name)
    decoded = json.loads(text)
    if not isinstance(decoded, dict):
        raise ValueError(f"{field_name} must decode to an object")
    return decoded


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


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

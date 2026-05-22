"""Prediction receipt contracts for IX-BlackFox-WorldTwin.

Receipts make prediction evidence portable, reviewable, and tamper-evident at
the artifact level. This module records what prediction was produced, when it
was receipted, which artifacts support it, and whether the receipt should move
toward human review or remain blocked.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.prediction import PredictionDisposition, PredictionResult
from ix_blackfox_worldtwin.reproducibility import ReproducibilityManifest

RECEIPT_SCHEMA_VERSION = "prediction-receipt-v1"
RECEIPT_ID_DIGEST_LENGTH = 16


class ReceiptReviewDecision(StrEnum):
    """Review decision encoded by a prediction receipt."""

    RECORD_ONLY = "record-only"
    HUMAN_REVIEW_REQUIRED = "human-review-required"
    EXECUTION_REVIEW_BLOCKED = "execution-review-blocked"
    BLOCKED = "execution-review-blocked"


@dataclass(frozen=True, slots=True)
class ReceiptArtifact:
    """A fingerprinted artifact captured inside a prediction receipt."""

    artifact_id: str
    artifact_type: str
    fingerprint: str
    source: str

    def __post_init__(self) -> None:
        """Validate and normalize a receipt artifact."""

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
        """Return a deterministic payload for hashing and chained receipts."""

        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "fingerprint": self.fingerprint,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class PredictionReceipt:
    """A reviewable receipt for one bounded prediction result."""

    receipt_id: str
    prediction_id: str
    scenario_id: str
    simulation_id: str
    created_at: datetime
    created_by: str
    review_decision: ReceiptReviewDecision
    prediction_disposition: PredictionDisposition
    final_state_id: str = ""
    final_state_fingerprint: str = ""
    artifacts: tuple[ReceiptArtifact, ...] = ()
    finding_codes: tuple[str, ...] = ()
    requires_human_authority: bool = True
    allowed_for_automatic_execution: bool = False
    notes: tuple[str, ...] = ()
    schema_version: str = RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a prediction receipt."""

        if not self.requires_human_authority:
            raise ValueError("prediction receipt must require human authority")
        if self.allowed_for_automatic_execution:
            raise ValueError("prediction receipt must never allow automatic execution")
        expected_decision = _derive_receipt_review_decision(self.prediction_disposition)
        if self.review_decision is not expected_decision:
            raise ValueError("receipt review decision must match prediction disposition")
        if not self.artifacts:
            raise ValueError("prediction receipt requires at least one artifact")

        object.__setattr__(self, "receipt_id", _require_non_empty(self.receipt_id, "receipt id"))
        object.__setattr__(
            self,
            "prediction_id",
            _require_non_empty(self.prediction_id, "prediction id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "simulation_id",
            _require_non_empty(self.simulation_id, "simulation id"),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "receipt created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "final_state_id",
            _require_non_empty(self.final_state_id, "final state id"),
        )
        object.__setattr__(
            self,
            "final_state_fingerprint",
            _require_non_empty(self.final_state_fingerprint, "final state fingerprint"),
        )
        object.__setattr__(self, "artifacts", _normalize_receipt_artifacts(self.artifacts))
        object.__setattr__(
            self,
            "finding_codes",
            _normalize_unique_text_tuple(self.finding_codes, "finding code"),
        )
        object.__setattr__(self, "notes", _normalize_unique_text_tuple(self.notes, "receipt note"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "receipt schema version"),
        )

    @property
    def blocks_execution_review(self) -> bool:
        """Return True when this receipt blocks execution review."""

        return self.review_decision is ReceiptReviewDecision.EXECUTION_REVIEW_BLOCKED

    @property
    def requires_human_review(self) -> bool:
        """Return True when this receipt requires human review."""

        return self.review_decision in {
            ReceiptReviewDecision.HUMAN_REVIEW_REQUIRED,
            ReceiptReviewDecision.EXECUTION_REVIEW_BLOCKED,
        }

    @property
    def ready_for_human_review(self) -> bool:
        """Return True when the receipt may enter human review or record-only archival."""

        return not self.blocks_execution_review

    def artifact_ids(self) -> tuple[str, ...]:
        """Return artifact ids in deterministic order."""

        return tuple(artifact.artifact_id for artifact in self.artifacts)

    def artifact_table(self) -> dict[str, str]:
        """Return artifact ids mapped to their fingerprints."""

        return {artifact.artifact_id: artifact.fingerprint for artifact in self.artifacts}

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and chained receipts."""

        return {
            "artifacts": [artifact.canonical_payload() for artifact in self.artifacts],
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "final_state_fingerprint": self.final_state_fingerprint,
            "final_state_id": self.final_state_id,
            "finding_codes": list(self.finding_codes),
            "notes": list(self.notes),
            "allowed_for_automatic_execution": self.allowed_for_automatic_execution,
            "prediction_disposition": self.prediction_disposition.value,
            "prediction_id": self.prediction_id,
            "receipt_id": self.receipt_id,
            "requires_human_authority": self.requires_human_authority,
            "review_decision": self.review_decision.value,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "simulation_id": self.simulation_id,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this receipt."""

        return _stable_sha256(self.canonical_payload())


def create_prediction_receipt(
    *,
    prediction: PredictionResult,
    created_at: datetime,
    created_by: str,
    reproducibility_manifest: ReproducibilityManifest | None = None,
    additional_artifacts: tuple[ReceiptArtifact, ...] = (),
    artifacts: tuple[ReceiptArtifact, ...] = (),
    notes: tuple[str, ...] = (),
    receipt_id: str | None = None,
) -> PredictionReceipt:
    """Create a prediction receipt from a bounded prediction result."""

    normalized_created_at = _require_aware_utc_datetime(created_at, "receipt created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_notes = _normalize_unique_text_tuple(notes, "receipt note")

    receipt_artifacts = [
        ReceiptArtifact(
            artifact_id=prediction.prediction_id,
            artifact_type="prediction-result",
            fingerprint=prediction.fingerprint(),
            source="prediction",
        ),
        ReceiptArtifact(
            artifact_id=prediction.final_state.state_id,
            artifact_type="prediction-final-state",
            fingerprint=prediction.final_state.fingerprint(),
            source="state",
        ),
    ]

    if reproducibility_manifest is not None:
        if reproducibility_manifest.manifest_id != prediction.reproducibility_manifest_id:
            raise ValueError(
                "reproducibility manifest id must match prediction reproducibility_manifest_id"
            )
        receipt_artifacts.append(
            ReceiptArtifact(
                artifact_id=reproducibility_manifest.manifest_id,
                artifact_type="reproducibility-manifest",
                fingerprint=reproducibility_manifest.fingerprint(),
                source="reproducibility",
            )
        )

    receipt_artifacts.extend(additional_artifacts)
    receipt_artifacts.extend(artifacts)
    normalized_artifacts = _normalize_receipt_artifacts(tuple(receipt_artifacts))
    review_decision = _derive_receipt_review_decision(prediction.disposition)
    finding_codes = prediction.finding_codes()
    resolved_receipt_id = receipt_id or make_prediction_receipt_id(
        prediction_id=prediction.prediction_id,
        scenario_id=prediction.scenario_id,
        simulation_id=prediction.simulation_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        review_decision=review_decision,
        prediction_disposition=prediction.disposition,
        final_state_id=prediction.final_state.state_id,
        final_state_fingerprint=prediction.final_state.fingerprint(),
        artifacts=normalized_artifacts,
        finding_codes=finding_codes,
        notes=normalized_notes,
    )

    return PredictionReceipt(
        receipt_id=resolved_receipt_id,
        prediction_id=prediction.prediction_id,
        scenario_id=prediction.scenario_id,
        simulation_id=prediction.simulation_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        review_decision=review_decision,
        prediction_disposition=prediction.disposition,
        final_state_id=prediction.final_state.state_id,
        final_state_fingerprint=prediction.final_state.fingerprint(),
        artifacts=normalized_artifacts,
        finding_codes=finding_codes,
        notes=normalized_notes,
    )


def make_prediction_receipt_id(
    *,
    prediction_id: str,
    scenario_id: str,
    simulation_id: str,
    created_at: datetime,
    created_by: str,
    review_decision: ReceiptReviewDecision,
    prediction_disposition: PredictionDisposition,
    final_state_id: str,
    final_state_fingerprint: str,
    artifacts: tuple[ReceiptArtifact, ...],
    finding_codes: tuple[str, ...],
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic prediction-receipt id."""

    payload = {
        "artifacts": [
            artifact.canonical_payload() for artifact in _normalize_receipt_artifacts(artifacts)
        ],
        "created_at": _require_aware_utc_datetime(
            created_at,
            "receipt created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "final_state_fingerprint": _require_non_empty(
            final_state_fingerprint,
            "final state fingerprint",
        ),
        "final_state_id": _require_non_empty(final_state_id, "final state id"),
        "finding_codes": list(_normalize_unique_text_tuple(finding_codes, "finding code")),
        "notes": list(_normalize_unique_text_tuple(notes, "receipt note")),
        "prediction_disposition": prediction_disposition.value,
        "prediction_id": _require_non_empty(prediction_id, "prediction id"),
        "review_decision": review_decision.value,
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "simulation_id": _require_non_empty(simulation_id, "simulation id"),
    }
    digest = _stable_sha256(payload)[:RECEIPT_ID_DIGEST_LENGTH]
    return f"prediction-receipt-{digest}"


def _derive_receipt_review_decision(
    disposition: PredictionDisposition,
) -> ReceiptReviewDecision:
    if disposition in {PredictionDisposition.DENY, PredictionDisposition.QUARANTINE}:
        return ReceiptReviewDecision.EXECUTION_REVIEW_BLOCKED
    if disposition in {PredictionDisposition.REVIEW, PredictionDisposition.CAUTION}:
        return ReceiptReviewDecision.HUMAN_REVIEW_REQUIRED
    return ReceiptReviewDecision.RECORD_ONLY


def _normalize_receipt_artifacts(
    artifacts: tuple[ReceiptArtifact, ...],
) -> tuple[ReceiptArtifact, ...]:
    if not artifacts:
        raise ValueError("prediction receipt requires at least one artifact")

    seen_artifact_ids: set[str] = set()
    normalized_artifacts: list[ReceiptArtifact] = []

    for artifact in artifacts:
        if artifact.artifact_id in seen_artifact_ids:
            raise ValueError(f"duplicate receipt artifact id: {artifact.artifact_id}")
        seen_artifact_ids.add(artifact.artifact_id)
        normalized_artifacts.append(artifact)

    return tuple(
        sorted(normalized_artifacts, key=lambda item: (item.artifact_type, item.artifact_id))
    )


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

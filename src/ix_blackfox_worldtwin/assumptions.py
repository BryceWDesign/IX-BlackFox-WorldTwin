"""Assumption ledger contracts for IX-BlackFox-WorldTwin.

WorldTwin predictions are only as honest as their assumptions. This module keeps
assumptions explicit, reviewable, evidence-linked, confidence-scored, and
staleness-aware so scenario predictions cannot hide fragile premises behind
clean-looking simulation output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.uncertainty import validate_confidence

ASSUMPTION_SCHEMA_VERSION = "assumption-ledger-v1"
ASSUMPTION_ID_DIGEST_LENGTH = 16


class AssumptionStatus(StrEnum):
    """Lifecycle status for an assumption in the WorldTwin ledger."""

    ACTIVE = "active"
    EXPIRED = "expired"
    DISPUTED = "disputed"
    RETIRED = "retired"


class AssumptionImpactLevel(StrEnum):
    """Impact level if an assumption is wrong."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssumptionCategory(StrEnum):
    """Supported assumption categories."""

    PHYSICAL = "physical"
    OPERATIONAL = "operational"
    POLICY = "policy"
    DATA_QUALITY = "data-quality"
    HUMAN_REVIEW = "human-review"
    MODEL_BEHAVIOR = "model-behavior"
    SCENARIO_BOUNDARY = "scenario-boundary"


@dataclass(frozen=True, slots=True)
class RequiredEvidence:
    """Evidence that should be supplied before an assumption is trusted further."""

    description: str
    required_before_execution: bool = True

    def __post_init__(self) -> None:
        """Validate and normalize required evidence."""

        object.__setattr__(
            self,
            "description",
            _require_non_empty(self.description, "required evidence description"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "description": self.description,
            "required_before_execution": self.required_before_execution,
        }


@dataclass(frozen=True, slots=True)
class AssumptionRecord:
    """A single explicit assumption used by a scenario or prediction."""

    assumption_id: str
    name: str
    category: AssumptionCategory
    statement: str
    confidence: float
    impact_if_wrong: AssumptionImpactLevel
    status: AssumptionStatus
    created_at: datetime
    owner: str
    evidence_ids: tuple[str, ...] = ()
    required_evidence: tuple[RequiredEvidence, ...] = ()
    expires_at: datetime | None = None
    tags: tuple[str, ...] = ()
    schema_version: str = ASSUMPTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize an assumption record."""

        created_at = _require_aware_utc_datetime(self.created_at, "assumption created_at")
        expires_at = None
        if self.expires_at is not None:
            expires_at = _require_aware_utc_datetime(self.expires_at, "assumption expires_at")
            if expires_at <= created_at:
                raise ValueError("assumption expires_at must be after created_at")

        object.__setattr__(
            self,
            "assumption_id",
            _require_non_empty(self.assumption_id, "assumption id"),
        )
        object.__setattr__(self, "name", _require_non_empty(self.name, "assumption name"))
        object.__setattr__(
            self,
            "statement",
            _require_non_empty(self.statement, "assumption statement"),
        )
        object.__setattr__(
            self,
            "confidence",
            validate_confidence(self.confidence, "assumption confidence"),
        )
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "owner", _require_non_empty(self.owner, "assumption owner"))
        object.__setattr__(
            self,
            "evidence_ids",
            _normalize_unique_text_tuple(self.evidence_ids, "evidence id"),
        )
        object.__setattr__(
            self,
            "required_evidence",
            _normalize_required_evidence(self.required_evidence),
        )
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "tags", _normalize_unique_text_tuple(self.tags, "assumption tag"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "assumption schema version"),
        )

    def is_stale_at(self, checked_at: datetime) -> bool:
        """Return True when the assumption is expired or past its expiry time."""

        normalized_checked_at = _require_aware_utc_datetime(checked_at, "assumption checked_at")
        if self.status is AssumptionStatus.EXPIRED:
            return True
        if self.expires_at is None:
            return False
        return normalized_checked_at >= self.expires_at

    def blocks_execution_without_evidence(self) -> bool:
        """Return True when required evidence is missing before execution review."""

        has_blocking_requirement = any(
            evidence.required_before_execution for evidence in self.required_evidence
        )
        return has_blocking_requirement and not self.evidence_ids

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return _canonical_assumption_payload(
            assumption_id=self.assumption_id,
            name=self.name,
            category=self.category,
            statement=self.statement,
            confidence=self.confidence,
            impact_if_wrong=self.impact_if_wrong,
            status=self.status,
            created_at=self.created_at,
            owner=self.owner,
            evidence_ids=self.evidence_ids,
            required_evidence=self.required_evidence,
            expires_at=self.expires_at,
            tags=self.tags,
            schema_version=self.schema_version,
        )

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this assumption."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class AssumptionLedger:
    """A deterministic collection of assumptions used by a scenario or prediction."""

    ledger_id: str
    assumptions: tuple[AssumptionRecord, ...]
    created_at: datetime
    owner: str
    scenario_id: str = ""
    notes: tuple[str, ...] = ()
    schema_version: str = ASSUMPTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize an assumption ledger."""

        object.__setattr__(self, "ledger_id", _require_non_empty(self.ledger_id, "ledger id"))
        object.__setattr__(
            self,
            "assumptions",
            _normalize_assumption_records(self.assumptions),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "ledger created_at"),
        )
        object.__setattr__(self, "owner", _require_non_empty(self.owner, "ledger owner"))
        object.__setattr__(self, "scenario_id", self.scenario_id.strip())
        object.__setattr__(self, "notes", _normalize_unique_text_tuple(self.notes, "ledger note"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "assumption schema version"),
        )

    def stale_assumptions_at(self, checked_at: datetime) -> tuple[AssumptionRecord, ...]:
        """Return assumptions that are stale at a supplied review time."""

        return tuple(
            assumption for assumption in self.assumptions if assumption.is_stale_at(checked_at)
        )

    def disputed_assumptions(self) -> tuple[AssumptionRecord, ...]:
        """Return assumptions currently marked as disputed."""

        return tuple(
            assumption
            for assumption in self.assumptions
            if assumption.status is AssumptionStatus.DISPUTED
        )

    def execution_blockers(self) -> tuple[AssumptionRecord, ...]:
        """Return assumptions that require missing evidence before execution review."""

        return tuple(
            assumption
            for assumption in self.assumptions
            if assumption.blocks_execution_without_evidence()
        )

    def lowest_confidence(self) -> float:
        """Return the lowest assumption confidence in the ledger."""

        return min(assumption.confidence for assumption in self.assumptions)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "assumptions": [assumption.canonical_payload() for assumption in self.assumptions],
            "created_at": self.created_at.isoformat(),
            "ledger_id": self.ledger_id,
            "notes": list(self.notes),
            "owner": self.owner,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this ledger."""

        return _stable_sha256(self.canonical_payload())


def create_assumption_record(
    *,
    name: str,
    category: AssumptionCategory,
    statement: str,
    confidence: float,
    impact_if_wrong: AssumptionImpactLevel,
    status: AssumptionStatus,
    created_at: datetime,
    owner: str,
    evidence_ids: tuple[str, ...] = (),
    required_evidence: tuple[RequiredEvidence, ...] = (),
    expires_at: datetime | None = None,
    tags: tuple[str, ...] = (),
    assumption_id: str | None = None,
) -> AssumptionRecord:
    """Create a validated assumption record with a deterministic id by default."""

    normalized_created_at = _require_aware_utc_datetime(created_at, "assumption created_at")
    normalized_expires_at = None
    if expires_at is not None:
        normalized_expires_at = _require_aware_utc_datetime(expires_at, "assumption expires_at")
        if normalized_expires_at <= normalized_created_at:
            raise ValueError("assumption expires_at must be after created_at")

    normalized_required_evidence = _normalize_required_evidence(required_evidence)
    normalized_evidence_ids = _normalize_unique_text_tuple(evidence_ids, "evidence id")
    normalized_tags = _normalize_unique_text_tuple(tags, "assumption tag")
    resolved_assumption_id = assumption_id or make_assumption_id(
        name=name,
        category=category,
        statement=statement,
        confidence=confidence,
        impact_if_wrong=impact_if_wrong,
        status=status,
        created_at=normalized_created_at,
        owner=owner,
        evidence_ids=normalized_evidence_ids,
        required_evidence=normalized_required_evidence,
        expires_at=normalized_expires_at,
        tags=normalized_tags,
    )

    return AssumptionRecord(
        assumption_id=resolved_assumption_id,
        name=name,
        category=category,
        statement=statement,
        confidence=confidence,
        impact_if_wrong=impact_if_wrong,
        status=status,
        created_at=normalized_created_at,
        owner=owner,
        evidence_ids=normalized_evidence_ids,
        required_evidence=normalized_required_evidence,
        expires_at=normalized_expires_at,
        tags=normalized_tags,
    )


def create_assumption_ledger(
    *,
    assumptions: tuple[AssumptionRecord, ...],
    created_at: datetime,
    owner: str,
    scenario_id: str = "",
    notes: tuple[str, ...] = (),
    ledger_id: str | None = None,
) -> AssumptionLedger:
    """Create a validated assumption ledger with a deterministic id by default."""

    normalized_assumptions = _normalize_assumption_records(assumptions)
    normalized_created_at = _require_aware_utc_datetime(created_at, "ledger created_at")
    normalized_owner = _require_non_empty(owner, "ledger owner")
    normalized_scenario_id = scenario_id.strip()
    normalized_notes = _normalize_unique_text_tuple(notes, "ledger note")
    resolved_ledger_id = ledger_id or make_assumption_ledger_id(
        assumptions=normalized_assumptions,
        created_at=normalized_created_at,
        owner=normalized_owner,
        scenario_id=normalized_scenario_id,
        notes=normalized_notes,
    )

    return AssumptionLedger(
        ledger_id=resolved_ledger_id,
        assumptions=normalized_assumptions,
        created_at=normalized_created_at,
        owner=normalized_owner,
        scenario_id=normalized_scenario_id,
        notes=normalized_notes,
    )


def make_assumption_id(
    *,
    name: str,
    category: AssumptionCategory,
    statement: str,
    confidence: float,
    impact_if_wrong: AssumptionImpactLevel,
    status: AssumptionStatus,
    created_at: datetime,
    owner: str,
    evidence_ids: tuple[str, ...] = (),
    required_evidence: tuple[RequiredEvidence, ...] = (),
    expires_at: datetime | None = None,
    tags: tuple[str, ...] = (),
) -> str:
    """Create a deterministic assumption id from an assumption payload."""

    payload = _canonical_assumption_payload(
        assumption_id="",
        name=_require_non_empty(name, "assumption name"),
        category=category,
        statement=_require_non_empty(statement, "assumption statement"),
        confidence=validate_confidence(confidence, "assumption confidence"),
        impact_if_wrong=impact_if_wrong,
        status=status,
        created_at=_require_aware_utc_datetime(created_at, "assumption created_at"),
        owner=_require_non_empty(owner, "assumption owner"),
        evidence_ids=_normalize_unique_text_tuple(evidence_ids, "evidence id"),
        required_evidence=_normalize_required_evidence(required_evidence),
        expires_at=_normalize_optional_datetime(expires_at, "assumption expires_at"),
        tags=_normalize_unique_text_tuple(tags, "assumption tag"),
        schema_version=ASSUMPTION_SCHEMA_VERSION,
    )
    digest = _stable_sha256(payload)[:ASSUMPTION_ID_DIGEST_LENGTH]
    return f"assumption-{digest}"


def make_assumption_ledger_id(
    *,
    assumptions: tuple[AssumptionRecord, ...],
    created_at: datetime,
    owner: str,
    scenario_id: str = "",
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic assumption ledger id."""

    payload = {
        "assumptions": [
            assumption.canonical_payload()
            for assumption in _normalize_assumption_records(assumptions)
        ],
        "created_at": _require_aware_utc_datetime(created_at, "ledger created_at").isoformat(),
        "notes": list(_normalize_unique_text_tuple(notes, "ledger note")),
        "owner": _require_non_empty(owner, "ledger owner"),
        "scenario_id": scenario_id.strip(),
        "schema_version": ASSUMPTION_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:ASSUMPTION_ID_DIGEST_LENGTH]
    return f"assumption-ledger-{digest}"


def _canonical_assumption_payload(
    *,
    assumption_id: str,
    name: str,
    category: AssumptionCategory,
    statement: str,
    confidence: float,
    impact_if_wrong: AssumptionImpactLevel,
    status: AssumptionStatus,
    created_at: datetime,
    owner: str,
    evidence_ids: tuple[str, ...],
    required_evidence: tuple[RequiredEvidence, ...],
    expires_at: datetime | None,
    tags: tuple[str, ...],
    schema_version: str,
) -> dict[str, Any]:
    return {
        "assumption_id": assumption_id,
        "category": category.value,
        "confidence": confidence,
        "created_at": created_at.isoformat(),
        "evidence_ids": list(evidence_ids),
        "expires_at": None if expires_at is None else expires_at.isoformat(),
        "impact_if_wrong": impact_if_wrong.value,
        "name": name,
        "owner": owner,
        "required_evidence": [evidence.canonical_payload() for evidence in required_evidence],
        "schema_version": schema_version,
        "statement": statement,
        "status": status.value,
        "tags": list(tags),
    }


def _normalize_assumption_records(
    assumptions: tuple[AssumptionRecord, ...],
) -> tuple[AssumptionRecord, ...]:
    if not assumptions:
        raise ValueError("assumption ledger requires at least one assumption")

    seen_ids: set[str] = set()
    normalized_assumptions: list[AssumptionRecord] = []

    for assumption in assumptions:
        if assumption.assumption_id in seen_ids:
            raise ValueError(f"duplicate assumption id: {assumption.assumption_id}")
        seen_ids.add(assumption.assumption_id)
        normalized_assumptions.append(assumption)

    return tuple(sorted(normalized_assumptions, key=lambda item: item.assumption_id))


def _normalize_required_evidence(
    required_evidence: tuple[RequiredEvidence, ...],
) -> tuple[RequiredEvidence, ...]:
    seen_descriptions: set[str] = set()
    normalized_required_evidence: list[RequiredEvidence] = []

    for evidence in required_evidence:
        if evidence.description in seen_descriptions:
            raise ValueError(f"duplicate required evidence: {evidence.description}")
        seen_descriptions.add(evidence.description)
        normalized_required_evidence.append(evidence)

    return tuple(sorted(normalized_required_evidence, key=lambda item: item.description))


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


def _normalize_optional_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _require_aware_utc_datetime(value, field_name)


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

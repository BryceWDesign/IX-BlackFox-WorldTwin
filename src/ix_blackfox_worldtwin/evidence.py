"""Evidence reference contracts for IX-BlackFox-WorldTwin.

Evidence references let WorldTwin attach provenance to observations,
simulations, tests, reviews, receipts, and external materials without turning
any single artifact into authority. The reference records what was used, when it
was captured, how it was hashed, and how it should be grouped for later
scenario, receipt, and reality-delta review.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

EVIDENCE_SCHEMA_VERSION = "evidence-reference-v1"
EVIDENCE_ID_DIGEST_LENGTH = 16
SHA256_HEX_LENGTH = 64


class EvidenceKind(StrEnum):
    """Supported evidence categories for bounded WorldTwin review."""

    OBSERVATION = "observation"
    TELEMETRY = "telemetry"
    SIMULATION = "simulation"
    TEST_RESULT = "test-result"
    POLICY = "policy"
    HUMAN_REVIEW = "human-review"
    EXTERNAL_DOCUMENT = "external-document"
    MODEL_OUTPUT = "model-output"
    RECEIPT = "receipt"


@dataclass(frozen=True, slots=True)
class EvidenceAttribute:
    """A deterministic key-value attribute attached to evidence."""

    key: str
    value: str

    def __post_init__(self) -> None:
        """Validate and normalize an evidence attribute."""

        object.__setattr__(self, "key", _require_non_empty(self.key, "evidence attribute key"))
        object.__setattr__(
            self, "value", _require_non_empty(self.value, "evidence attribute value")
        )

    def canonical_payload(self) -> dict[str, str]:
        """Return a deterministic payload for hashing."""

        return {"key": self.key, "value": self.value}


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """A bounded reference to an evidence artifact used by WorldTwin."""

    evidence_id: str
    kind: EvidenceKind
    title: str
    source: str
    captured_at: datetime
    summary: str
    content_hash: str
    uri: str = ""
    tags: tuple[str, ...] = ()
    attributes: tuple[EvidenceAttribute, ...] = ()
    schema_version: str = EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize an evidence reference."""

        object.__setattr__(self, "evidence_id", _require_non_empty(self.evidence_id, "evidence id"))
        object.__setattr__(self, "title", _require_non_empty(self.title, "evidence title"))
        object.__setattr__(self, "source", _require_non_empty(self.source, "evidence source"))
        object.__setattr__(self, "summary", _require_non_empty(self.summary, "evidence summary"))
        object.__setattr__(self, "content_hash", _require_sha256_hex(self.content_hash))
        object.__setattr__(self, "uri", self.uri.strip())
        object.__setattr__(self, "tags", _normalize_text_tuple(self.tags, "evidence tag"))
        object.__setattr__(self, "attributes", _normalize_attributes(self.attributes))
        object.__setattr__(
            self,
            "captured_at",
            _require_aware_utc_datetime(self.captured_at, "evidence captured_at"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "evidence schema version"),
        )

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipt generation."""

        return _canonical_evidence_payload(
            evidence_id=self.evidence_id,
            kind=self.kind,
            title=self.title,
            source=self.source,
            captured_at=self.captured_at,
            summary=self.summary,
            content_hash=self.content_hash,
            uri=self.uri,
            tags=self.tags,
            attributes=self.attributes,
            schema_version=self.schema_version,
        )

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this evidence reference."""

        return _stable_sha256(self.canonical_payload())


def create_evidence_reference(
    *,
    kind: EvidenceKind,
    title: str,
    source: str,
    captured_at: datetime,
    summary: str,
    content: str | bytes,
    uri: str = "",
    tags: tuple[str, ...] = (),
    attributes: tuple[EvidenceAttribute, ...] = (),
    evidence_id: str | None = None,
) -> EvidenceReference:
    """Create an evidence reference by hashing raw evidence content."""

    return create_evidence_reference_from_hash(
        kind=kind,
        title=title,
        source=source,
        captured_at=captured_at,
        summary=summary,
        content_hash=hash_evidence_content(content),
        uri=uri,
        tags=tags,
        attributes=attributes,
        evidence_id=evidence_id,
    )


def create_evidence_reference_from_hash(
    *,
    kind: EvidenceKind,
    title: str,
    source: str,
    captured_at: datetime,
    summary: str,
    content_hash: str,
    uri: str = "",
    tags: tuple[str, ...] = (),
    attributes: tuple[EvidenceAttribute, ...] = (),
    evidence_id: str | None = None,
) -> EvidenceReference:
    """Create an evidence reference from a precomputed SHA-256 content hash."""

    normalized_title = _require_non_empty(title, "evidence title")
    normalized_source = _require_non_empty(source, "evidence source")
    normalized_captured_at = _require_aware_utc_datetime(captured_at, "evidence captured_at")
    normalized_summary = _require_non_empty(summary, "evidence summary")
    normalized_content_hash = _require_sha256_hex(content_hash)
    normalized_uri = uri.strip()
    normalized_tags = _normalize_text_tuple(tags, "evidence tag")
    normalized_attributes = _normalize_attributes(attributes)
    resolved_evidence_id = evidence_id or make_evidence_id(
        kind=kind,
        title=normalized_title,
        source=normalized_source,
        captured_at=normalized_captured_at,
        summary=normalized_summary,
        content_hash=normalized_content_hash,
        uri=normalized_uri,
        tags=normalized_tags,
        attributes=normalized_attributes,
    )

    return EvidenceReference(
        evidence_id=resolved_evidence_id,
        kind=kind,
        title=normalized_title,
        source=normalized_source,
        captured_at=normalized_captured_at,
        summary=normalized_summary,
        content_hash=normalized_content_hash,
        uri=normalized_uri,
        tags=normalized_tags,
        attributes=normalized_attributes,
    )


def hash_evidence_content(content: str | bytes) -> str:
    """Return the SHA-256 hash for evidence content."""

    encoded_content = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(encoded_content).hexdigest()


def make_evidence_id(
    *,
    kind: EvidenceKind,
    title: str,
    source: str,
    captured_at: datetime,
    summary: str,
    content_hash: str,
    uri: str = "",
    tags: tuple[str, ...] = (),
    attributes: tuple[EvidenceAttribute, ...] = (),
) -> str:
    """Create a deterministic evidence id from the semantic evidence payload."""

    payload = _canonical_evidence_payload(
        evidence_id="",
        kind=kind,
        title=_require_non_empty(title, "evidence title"),
        source=_require_non_empty(source, "evidence source"),
        captured_at=_require_aware_utc_datetime(captured_at, "evidence captured_at"),
        summary=_require_non_empty(summary, "evidence summary"),
        content_hash=_require_sha256_hex(content_hash),
        uri=uri.strip(),
        tags=_normalize_text_tuple(tags, "evidence tag"),
        attributes=_normalize_attributes(attributes),
        schema_version=EVIDENCE_SCHEMA_VERSION,
    )
    digest = _stable_sha256(payload)[:EVIDENCE_ID_DIGEST_LENGTH]
    return f"{kind.value}-evidence-{digest}"


def _canonical_evidence_payload(
    *,
    evidence_id: str,
    kind: EvidenceKind,
    title: str,
    source: str,
    captured_at: datetime,
    summary: str,
    content_hash: str,
    uri: str,
    tags: tuple[str, ...],
    attributes: tuple[EvidenceAttribute, ...],
    schema_version: str,
) -> dict[str, Any]:
    return {
        "attributes": [attribute.canonical_payload() for attribute in attributes],
        "captured_at": captured_at.isoformat(),
        "content_hash": content_hash,
        "evidence_id": evidence_id,
        "kind": kind.value,
        "schema_version": schema_version,
        "source": source,
        "summary": summary,
        "tags": list(tags),
        "title": title,
        "uri": uri,
    }


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()


def _normalize_attributes(
    attributes: tuple[EvidenceAttribute, ...],
) -> tuple[EvidenceAttribute, ...]:
    seen_keys: set[str] = set()
    normalized_attributes: list[EvidenceAttribute] = []

    for attribute in attributes:
        if attribute.key in seen_keys:
            raise ValueError(f"duplicate evidence attribute: {attribute.key}")
        seen_keys.add(attribute.key)
        normalized_attributes.append(attribute)

    return tuple(sorted(normalized_attributes, key=lambda attribute: attribute.key))


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


def _require_sha256_hex(value: str) -> str:
    normalized_value = _require_non_empty(value, "evidence content hash").casefold()
    if len(normalized_value) != SHA256_HEX_LENGTH:
        raise ValueError("evidence content hash must be a SHA-256 hex digest")

    try:
        int(normalized_value, 16)
    except ValueError as exc:
        raise ValueError("evidence content hash must be a SHA-256 hex digest") from exc

    return normalized_value


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)

"""Tamper-evident receipt-chain integrity for IX-BlackFox-WorldTwin.

A single receipt proves one prediction package at one point in time. A receipt
chain proves ordering, continuity, and later tamper detection across multiple
prediction receipts. The chain is deterministic, dependency-light, and designed
for later BlackFox-compatible evidence handoff.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.receipts import PredictionReceipt

RECEIPT_CHAIN_SCHEMA_VERSION = "receipt-chain-v1"
RECEIPT_CHAIN_ID_DIGEST_LENGTH = 16
GENESIS_PREVIOUS_ENTRY_HASH = "GENESIS"


class ReceiptChainValidationStatus(StrEnum):
    """Validation status for a receipt chain."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ReceiptChainEntry:
    """One ordered entry in a tamper-evident prediction-receipt chain."""

    entry_id: str
    sequence_number: int
    receipt_id: str
    receipt_fingerprint: str
    previous_entry_hash: str
    entry_hash: str
    created_at: datetime
    created_by: str
    schema_version: str = RECEIPT_CHAIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a receipt-chain entry."""

        if self.sequence_number < 1:
            raise ValueError("receipt-chain sequence_number must be greater than zero")

        object.__setattr__(self, "entry_id", _require_non_empty(self.entry_id, "entry id"))
        object.__setattr__(
            self,
            "receipt_id",
            _require_non_empty(self.receipt_id, "receipt id"),
        )
        object.__setattr__(
            self,
            "receipt_fingerprint",
            _require_non_empty(self.receipt_fingerprint, "receipt fingerprint"),
        )
        object.__setattr__(
            self,
            "previous_entry_hash",
            _require_non_empty(self.previous_entry_hash, "previous entry hash"),
        )
        object.__setattr__(
            self,
            "entry_hash",
            _require_non_empty(self.entry_hash, "entry hash"),
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "entry created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "receipt-chain schema version"),
        )

    def payload_without_entry_hash(self) -> dict[str, Any]:
        """Return the deterministic payload used to calculate entry_hash."""

        return {
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "entry_id": self.entry_id,
            "previous_entry_hash": self.previous_entry_hash,
            "receipt_fingerprint": self.receipt_fingerprint,
            "receipt_id": self.receipt_id,
            "schema_version": self.schema_version,
            "sequence_number": self.sequence_number,
        }

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        payload = self.payload_without_entry_hash()
        payload["entry_hash"] = self.entry_hash
        return payload

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this entry."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ReceiptChain:
    """A tamper-evident chain of ordered prediction receipts."""

    chain_id: str
    entries: tuple[ReceiptChainEntry, ...]
    created_at: datetime
    created_by: str
    notes: tuple[str, ...] = ()
    schema_version: str = RECEIPT_CHAIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a receipt chain."""

        if not self.entries:
            raise ValueError("receipt chain requires at least one entry")

        object.__setattr__(self, "chain_id", _require_non_empty(self.chain_id, "chain id"))
        object.__setattr__(
            self, "entries", tuple(sorted(self.entries, key=lambda item: item.sequence_number))
        )
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "chain created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(self, "notes", _normalize_unique_text_tuple(self.notes, "chain note"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "receipt-chain schema version"),
        )

        sequence_numbers = tuple(entry.sequence_number for entry in self.entries)
        expected_sequence = tuple(range(1, len(self.entries) + 1))
        if sequence_numbers != expected_sequence:
            raise ValueError("receipt chain entries must use contiguous sequence numbers")

        receipt_ids = tuple(entry.receipt_id for entry in self.entries)
        if len(set(receipt_ids)) != len(receipt_ids):
            raise ValueError("receipt chain contains duplicate receipt ids")

    @property
    def head(self) -> ReceiptChainEntry:
        """Return the newest entry in the chain."""

        return self.entries[-1]

    @property
    def tail(self) -> ReceiptChainEntry:
        """Return the first entry in the chain."""

        return self.entries[0]

    def receipt_ids(self) -> tuple[str, ...]:
        """Return receipt ids in chain order."""

        return tuple(entry.receipt_id for entry in self.entries)

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and handoff."""

        return {
            "chain_id": self.chain_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "entries": [entry.canonical_payload() for entry in self.entries],
            "notes": list(self.notes),
            "schema_version": self.schema_version,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this receipt chain."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ReceiptChainValidationResult:
    """Result of validating a receipt chain."""

    chain_id: str
    status: ReceiptChainValidationStatus
    checked_at: datetime
    checked_by: str
    issues: tuple[str, ...] = ()
    schema_version: str = RECEIPT_CHAIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a receipt-chain validation result."""

        expected_status = (
            ReceiptChainValidationStatus.PASS
            if not self.issues
            else ReceiptChainValidationStatus.FAIL
        )
        if self.status is not expected_status:
            raise ValueError("receipt-chain validation status must match issue state")

        object.__setattr__(self, "chain_id", _require_non_empty(self.chain_id, "chain id"))
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
            _require_non_empty(self.schema_version, "receipt-chain schema version"),
        )

    @property
    def passed(self) -> bool:
        """Return True when receipt-chain validation passed."""

        return self.status is ReceiptChainValidationStatus.PASS

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and handoff."""

        return {
            "chain_id": self.chain_id,
            "checked_at": self.checked_at.isoformat(),
            "checked_by": self.checked_by,
            "issues": list(self.issues),
            "schema_version": self.schema_version,
            "status": self.status.value,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this validation result."""

        return _stable_sha256(self.canonical_payload())


def create_receipt_chain(
    *,
    receipts: tuple[PredictionReceipt, ...],
    created_at: datetime,
    created_by: str,
    notes: tuple[str, ...] = (),
    chain_id: str | None = None,
) -> ReceiptChain:
    """Create a tamper-evident receipt chain from prediction receipts."""

    normalized_receipts = _normalize_receipts(receipts)
    normalized_created_at = _require_aware_utc_datetime(created_at, "chain created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_notes = _normalize_unique_text_tuple(notes, "chain note")
    entries = _build_chain_entries(
        receipts=normalized_receipts,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        previous_entry_hash=GENESIS_PREVIOUS_ENTRY_HASH,
        starting_sequence_number=1,
    )
    resolved_chain_id = chain_id or make_receipt_chain_id(
        entries=entries,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        notes=normalized_notes,
    )

    return ReceiptChain(
        chain_id=resolved_chain_id,
        entries=entries,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        notes=normalized_notes,
    )


def append_receipt_to_chain(
    *,
    chain: ReceiptChain,
    receipt: PredictionReceipt,
    created_at: datetime,
    created_by: str,
) -> ReceiptChain:
    """Return a new chain with one prediction receipt appended."""

    if receipt.receipt_id in chain.receipt_ids():
        raise ValueError(f"receipt already exists in chain: {receipt.receipt_id}")

    normalized_created_at = _require_aware_utc_datetime(created_at, "entry created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    new_entry = _build_chain_entries(
        receipts=(receipt,),
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        previous_entry_hash=chain.head.entry_hash,
        starting_sequence_number=chain.head.sequence_number + 1,
    )[0]
    new_entries = (*chain.entries, new_entry)
    new_chain_id = make_receipt_chain_id(
        entries=new_entries,
        created_at=chain.created_at,
        created_by=chain.created_by,
        notes=chain.notes,
    )

    return ReceiptChain(
        chain_id=new_chain_id,
        entries=new_entries,
        created_at=chain.created_at,
        created_by=chain.created_by,
        notes=chain.notes,
    )


def validate_receipt_chain(
    *,
    chain: ReceiptChain,
    receipts: tuple[PredictionReceipt, ...],
    checked_at: datetime,
    checked_by: str,
) -> ReceiptChainValidationResult:
    """Validate chain continuity and receipt fingerprints."""

    normalized_receipts = _normalize_receipts(receipts)
    receipts_by_id = {receipt.receipt_id: receipt for receipt in normalized_receipts}
    issues: list[str] = []

    if chain.tail.previous_entry_hash != GENESIS_PREVIOUS_ENTRY_HASH:
        issues.append("first entry does not reference genesis previous hash")

    previous_hash = GENESIS_PREVIOUS_ENTRY_HASH
    for expected_sequence, entry in enumerate(chain.entries, start=1):
        if entry.sequence_number != expected_sequence:
            issues.append(f"entry {entry.entry_id} has non-contiguous sequence number")

        if entry.previous_entry_hash != previous_hash:
            issues.append(f"entry {entry.entry_id} has invalid previous_entry_hash")

        expected_entry_hash = make_receipt_chain_entry_hash(
            entry_id=entry.entry_id,
            sequence_number=entry.sequence_number,
            receipt_id=entry.receipt_id,
            receipt_fingerprint=entry.receipt_fingerprint,
            previous_entry_hash=entry.previous_entry_hash,
            created_at=entry.created_at,
            created_by=entry.created_by,
        )
        if entry.entry_hash != expected_entry_hash:
            issues.append(f"entry {entry.entry_id} has invalid entry_hash")

        receipt = receipts_by_id.get(entry.receipt_id)
        if receipt is None:
            issues.append(f"entry {entry.entry_id} references missing receipt {entry.receipt_id}")
        elif receipt.fingerprint() != entry.receipt_fingerprint:
            issues.append(f"entry {entry.entry_id} receipt fingerprint mismatch")

        previous_hash = entry.entry_hash

    status = ReceiptChainValidationStatus.PASS if not issues else ReceiptChainValidationStatus.FAIL

    return ReceiptChainValidationResult(
        chain_id=chain.chain_id,
        status=status,
        checked_at=checked_at,
        checked_by=checked_by,
        issues=tuple(sorted(issues)),
    )


def make_receipt_chain_entry_id(
    *,
    sequence_number: int,
    receipt_id: str,
    receipt_fingerprint: str,
    previous_entry_hash: str,
    created_at: datetime,
    created_by: str,
) -> str:
    """Create a deterministic receipt-chain entry id."""

    payload = {
        "created_at": _require_aware_utc_datetime(created_at, "entry created_at").isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "previous_entry_hash": _require_non_empty(previous_entry_hash, "previous entry hash"),
        "receipt_fingerprint": _require_non_empty(receipt_fingerprint, "receipt fingerprint"),
        "receipt_id": _require_non_empty(receipt_id, "receipt id"),
        "schema_version": RECEIPT_CHAIN_SCHEMA_VERSION,
        "sequence_number": _require_positive_int(sequence_number, "sequence number"),
    }
    digest = _stable_sha256(payload)[:RECEIPT_CHAIN_ID_DIGEST_LENGTH]
    return f"receipt-chain-entry-{digest}"


def make_receipt_chain_entry_hash(
    *,
    entry_id: str,
    sequence_number: int,
    receipt_id: str,
    receipt_fingerprint: str,
    previous_entry_hash: str,
    created_at: datetime,
    created_by: str,
) -> str:
    """Create the deterministic tamper-evident hash for one chain entry."""

    payload = {
        "created_at": _require_aware_utc_datetime(created_at, "entry created_at").isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "entry_id": _require_non_empty(entry_id, "entry id"),
        "previous_entry_hash": _require_non_empty(previous_entry_hash, "previous entry hash"),
        "receipt_fingerprint": _require_non_empty(receipt_fingerprint, "receipt fingerprint"),
        "receipt_id": _require_non_empty(receipt_id, "receipt id"),
        "schema_version": RECEIPT_CHAIN_SCHEMA_VERSION,
        "sequence_number": _require_positive_int(sequence_number, "sequence number"),
    }
    return _stable_sha256(payload)


def make_receipt_chain_id(
    *,
    entries: tuple[ReceiptChainEntry, ...],
    created_at: datetime,
    created_by: str,
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic receipt-chain id."""

    if not entries:
        raise ValueError("receipt chain id requires at least one entry")

    payload = {
        "created_at": _require_aware_utc_datetime(created_at, "chain created_at").isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "entries": [entry.canonical_payload() for entry in entries],
        "notes": list(_normalize_unique_text_tuple(notes, "chain note")),
        "schema_version": RECEIPT_CHAIN_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:RECEIPT_CHAIN_ID_DIGEST_LENGTH]
    return f"receipt-chain-{digest}"


def _build_chain_entries(
    *,
    receipts: tuple[PredictionReceipt, ...],
    created_at: datetime,
    created_by: str,
    previous_entry_hash: str,
    starting_sequence_number: int,
) -> tuple[ReceiptChainEntry, ...]:
    entries: list[ReceiptChainEntry] = []
    current_previous_hash = previous_entry_hash

    for offset, receipt in enumerate(receipts):
        sequence_number = starting_sequence_number + offset
        receipt_fingerprint = receipt.fingerprint()
        entry_id = make_receipt_chain_entry_id(
            sequence_number=sequence_number,
            receipt_id=receipt.receipt_id,
            receipt_fingerprint=receipt_fingerprint,
            previous_entry_hash=current_previous_hash,
            created_at=created_at,
            created_by=created_by,
        )
        entry_hash = make_receipt_chain_entry_hash(
            entry_id=entry_id,
            sequence_number=sequence_number,
            receipt_id=receipt.receipt_id,
            receipt_fingerprint=receipt_fingerprint,
            previous_entry_hash=current_previous_hash,
            created_at=created_at,
            created_by=created_by,
        )
        entry = ReceiptChainEntry(
            entry_id=entry_id,
            sequence_number=sequence_number,
            receipt_id=receipt.receipt_id,
            receipt_fingerprint=receipt_fingerprint,
            previous_entry_hash=current_previous_hash,
            entry_hash=entry_hash,
            created_at=created_at,
            created_by=created_by,
        )
        entries.append(entry)
        current_previous_hash = entry_hash

    return tuple(entries)


def _normalize_receipts(receipts: tuple[PredictionReceipt, ...]) -> tuple[PredictionReceipt, ...]:
    if not receipts:
        raise ValueError("receipt chain requires at least one receipt")

    receipt_ids = tuple(receipt.receipt_id for receipt in receipts)
    if len(set(receipt_ids)) != len(receipt_ids):
        raise ValueError("receipt chain contains duplicate receipt ids")

    return receipts


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


def _require_positive_int(value: int, field_name: str) -> int:
    if value < 1:
        raise ValueError(f"{field_name} must be greater than zero")
    return value


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

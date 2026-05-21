from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

import ix_blackfox_worldtwin as worldtwin


def _captured_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_hash_evidence_content_matches_for_text_and_bytes() -> None:
    assert worldtwin.hash_evidence_content("same content") == worldtwin.hash_evidence_content(
        b"same content"
    )


def test_create_evidence_reference_hashes_content_and_normalizes_fields() -> None:
    evidence = worldtwin.create_evidence_reference(
        kind=worldtwin.EvidenceKind.TELEMETRY,
        title=" Sensor packet ",
        source=" sensor-feed-alpha ",
        captured_at=_captured_at(),
        summary=" high-frequency thermal telemetry ",
        content="temperature=72.5",
        uri=" file://telemetry.json ",
        tags=(" thermal ", "sensor"),
        attributes=(worldtwin.EvidenceAttribute(" sample_rate_hz ", " 10 "),),
    )

    assert evidence.evidence_id.startswith("telemetry-evidence-")
    assert evidence.kind is worldtwin.EvidenceKind.TELEMETRY
    assert evidence.title == "Sensor packet"
    assert evidence.source == "sensor-feed-alpha"
    assert evidence.summary == "high-frequency thermal telemetry"
    assert evidence.content_hash == worldtwin.hash_evidence_content("temperature=72.5")
    assert evidence.uri == "file://telemetry.json"
    assert evidence.tags == ("thermal", "sensor")
    assert evidence.attributes == (worldtwin.EvidenceAttribute("sample_rate_hz", "10"),)
    assert evidence.schema_version == worldtwin.EVIDENCE_SCHEMA_VERSION


def test_create_evidence_reference_from_hash_preserves_precomputed_hash() -> None:
    content_hash = worldtwin.hash_evidence_content("simulation output")
    evidence = worldtwin.create_evidence_reference_from_hash(
        kind=worldtwin.EvidenceKind.SIMULATION,
        title="Simulation branch A",
        source="deterministic-kernel",
        captured_at=_captured_at(),
        summary="Bounded simulation output for branch A.",
        content_hash=content_hash,
    )

    assert evidence.content_hash == content_hash
    assert evidence.evidence_id.startswith("simulation-evidence-")


def test_evidence_id_is_deterministic_when_attributes_are_reordered() -> None:
    content_hash = worldtwin.hash_evidence_content("policy text")
    first = worldtwin.make_evidence_id(
        kind=worldtwin.EvidenceKind.POLICY,
        title="Policy snapshot",
        source="policy-engine",
        captured_at=_captured_at(),
        summary="Policy used during the run.",
        content_hash=content_hash,
        attributes=(worldtwin.EvidenceAttribute("b", "2"), worldtwin.EvidenceAttribute("a", "1")),
    )
    second = worldtwin.make_evidence_id(
        kind=worldtwin.EvidenceKind.POLICY,
        title="Policy snapshot",
        source="policy-engine",
        captured_at=_captured_at(),
        summary="Policy used during the run.",
        content_hash=content_hash,
        attributes=(worldtwin.EvidenceAttribute("a", "1"), worldtwin.EvidenceAttribute("b", "2")),
    )

    assert first == second


def test_evidence_reference_fingerprint_is_stable_for_same_semantic_payload() -> None:
    content_hash = worldtwin.hash_evidence_content("review text")
    evidence_id = worldtwin.make_evidence_id(
        kind=worldtwin.EvidenceKind.HUMAN_REVIEW,
        title="Human review note",
        source="reviewer",
        captured_at=_captured_at(),
        summary="Reviewer asked for caution.",
        content_hash=content_hash,
    )
    first = worldtwin.create_evidence_reference_from_hash(
        kind=worldtwin.EvidenceKind.HUMAN_REVIEW,
        title="Human review note",
        source="reviewer",
        captured_at=_captured_at(),
        summary="Reviewer asked for caution.",
        content_hash=content_hash,
        evidence_id=evidence_id,
    )
    second = worldtwin.create_evidence_reference_from_hash(
        kind=worldtwin.EvidenceKind.HUMAN_REVIEW,
        title="Human review note",
        source="reviewer",
        captured_at=_captured_at(),
        summary="Reviewer asked for caution.",
        content_hash=content_hash,
        evidence_id=evidence_id,
    )

    assert first.fingerprint() == second.fingerprint()


def test_evidence_reference_rejects_bad_hash() -> None:
    with pytest.raises(ValueError, match="SHA-256 hex digest"):
        worldtwin.create_evidence_reference_from_hash(
            kind=worldtwin.EvidenceKind.TEST_RESULT,
            title="Test result",
            source="pytest",
            captured_at=_captured_at(),
            summary="Test output.",
            content_hash="not-a-sha256",
        )


def test_evidence_reference_rejects_naive_captured_at() -> None:
    with pytest.raises(ValueError, match="evidence captured_at must be timezone-aware"):
        worldtwin.create_evidence_reference(
            kind=worldtwin.EvidenceKind.OBSERVATION,
            title="Observation",
            source="observer",
            captured_at=datetime(2026, 1, 1, 12, 0),
            summary="Observation summary.",
            content="observation",
        )


def test_evidence_reference_normalizes_timezone_to_utc() -> None:
    local_time = datetime(2026, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=-8)))
    evidence = worldtwin.create_evidence_reference(
        kind=worldtwin.EvidenceKind.OBSERVATION,
        title="Observation",
        source="observer",
        captured_at=local_time,
        summary="Observation summary.",
        content="observation",
    )

    assert evidence.captured_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_evidence_reference_rejects_duplicate_attributes() -> None:
    with pytest.raises(ValueError, match="duplicate evidence attribute: channel"):
        worldtwin.create_evidence_reference(
            kind=worldtwin.EvidenceKind.TELEMETRY,
            title="Telemetry",
            source="sensor",
            captured_at=_captured_at(),
            summary="Telemetry summary.",
            content="telemetry",
            attributes=(
                worldtwin.EvidenceAttribute("channel", "a"),
                worldtwin.EvidenceAttribute("channel", "b"),
            ),
        )

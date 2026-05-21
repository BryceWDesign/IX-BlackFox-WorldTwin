from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_required_evidence_normalizes_description() -> None:
    evidence = worldtwin.RequiredEvidence(" sensor calibration receipt ")

    assert evidence.description == "sensor calibration receipt"
    assert evidence.required_before_execution is True


def test_assumption_record_tracks_confidence_status_impact_and_staleness() -> None:
    assumption = worldtwin.create_assumption_record(
        name="Thermal sensor remains calibrated",
        category=worldtwin.AssumptionCategory.DATA_QUALITY,
        statement="The thermal sensor was calibrated before the scenario run.",
        confidence=0.82,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.HIGH,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        evidence_ids=("evidence-calibration",),
        required_evidence=(worldtwin.RequiredEvidence("calibration receipt"),),
        expires_at=_created_at() + timedelta(days=30),
        tags=("thermal", "sensor"),
    )

    assert assumption.assumption_id.startswith("assumption-")
    assert assumption.schema_version == worldtwin.ASSUMPTION_SCHEMA_VERSION
    assert assumption.name == "Thermal sensor remains calibrated"
    assert assumption.confidence == 0.82
    assert assumption.impact_if_wrong is worldtwin.AssumptionImpactLevel.HIGH
    assert assumption.status is worldtwin.AssumptionStatus.ACTIVE
    assert assumption.evidence_ids == ("evidence-calibration",)
    assert assumption.required_evidence == (worldtwin.RequiredEvidence("calibration receipt"),)
    assert assumption.tags == ("sensor", "thermal")
    assert assumption.is_stale_at(_created_at() + timedelta(days=1)) is False
    assert assumption.is_stale_at(_created_at() + timedelta(days=31)) is True
    assert assumption.blocks_execution_without_evidence() is False


def test_assumption_record_blocks_execution_when_required_evidence_is_missing() -> None:
    assumption = worldtwin.create_assumption_record(
        name="Telemetry source is authenticated",
        category=worldtwin.AssumptionCategory.DATA_QUALITY,
        statement="The telemetry source identity is authenticated.",
        confidence=0.60,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.CRITICAL,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        required_evidence=(worldtwin.RequiredEvidence("source authentication receipt"),),
    )

    assert assumption.blocks_execution_without_evidence() is True


def test_expired_assumption_is_stale_even_without_expiry_time() -> None:
    assumption = worldtwin.create_assumption_record(
        name="Old policy remains valid",
        category=worldtwin.AssumptionCategory.POLICY,
        statement="The previous policy snapshot remains valid.",
        confidence=0.40,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.MEDIUM,
        status=worldtwin.AssumptionStatus.EXPIRED,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
    )

    assert assumption.is_stale_at(_created_at()) is True


def test_assumption_record_rejects_invalid_expiry_time() -> None:
    with pytest.raises(ValueError, match="assumption expires_at must be after created_at"):
        worldtwin.create_assumption_record(
            name="Invalid expiry",
            category=worldtwin.AssumptionCategory.OPERATIONAL,
            statement="This assumption has an invalid expiry time.",
            confidence=0.5,
            impact_if_wrong=worldtwin.AssumptionImpactLevel.LOW,
            status=worldtwin.AssumptionStatus.ACTIVE,
            created_at=_created_at(),
            owner="worldtwin-test-suite",
            expires_at=_created_at(),
        )


def test_assumption_record_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="assumption created_at must be timezone-aware"):
        worldtwin.create_assumption_record(
            name="Naive timestamp",
            category=worldtwin.AssumptionCategory.OPERATIONAL,
            statement="This assumption has a naive created_at timestamp.",
            confidence=0.5,
            impact_if_wrong=worldtwin.AssumptionImpactLevel.LOW,
            status=worldtwin.AssumptionStatus.ACTIVE,
            created_at=datetime(2026, 1, 1, 12, 0),
            owner="worldtwin-test-suite",
        )


def test_assumption_record_normalizes_timezone_to_utc() -> None:
    local_time = datetime(2026, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=-8)))
    assumption = worldtwin.create_assumption_record(
        name="Local timestamp",
        category=worldtwin.AssumptionCategory.OPERATIONAL,
        statement="This assumption should normalize to UTC.",
        confidence=0.5,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.LOW,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=local_time,
        owner="worldtwin-test-suite",
    )

    assert assumption.created_at == _created_at()


def test_assumption_record_rejects_duplicate_required_evidence() -> None:
    with pytest.raises(ValueError, match="duplicate required evidence: calibration receipt"):
        worldtwin.create_assumption_record(
            name="Duplicate evidence requirement",
            category=worldtwin.AssumptionCategory.DATA_QUALITY,
            statement="This assumption has duplicate required evidence.",
            confidence=0.5,
            impact_if_wrong=worldtwin.AssumptionImpactLevel.LOW,
            status=worldtwin.AssumptionStatus.ACTIVE,
            created_at=_created_at(),
            owner="worldtwin-test-suite",
            required_evidence=(
                worldtwin.RequiredEvidence("calibration receipt"),
                worldtwin.RequiredEvidence("calibration receipt"),
            ),
        )


def test_assumption_ledger_reports_stale_disputed_blocking_and_lowest_confidence() -> None:
    active = worldtwin.create_assumption_record(
        name="Telemetry source is authenticated",
        category=worldtwin.AssumptionCategory.DATA_QUALITY,
        statement="The telemetry source identity is authenticated.",
        confidence=0.60,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.CRITICAL,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        required_evidence=(worldtwin.RequiredEvidence("source authentication receipt"),),
    )
    disputed = worldtwin.create_assumption_record(
        name="Policy snapshot remains valid",
        category=worldtwin.AssumptionCategory.POLICY,
        statement="The policy snapshot still applies.",
        confidence=0.42,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.HIGH,
        status=worldtwin.AssumptionStatus.DISPUTED,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        evidence_ids=("policy-evidence",),
    )
    expiring = worldtwin.create_assumption_record(
        name="Scenario boundary remains stable",
        category=worldtwin.AssumptionCategory.SCENARIO_BOUNDARY,
        statement="The scenario boundary remains stable during review.",
        confidence=0.80,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.MEDIUM,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        evidence_ids=("boundary-evidence",),
        expires_at=_created_at() + timedelta(hours=1),
    )
    ledger = worldtwin.create_assumption_ledger(
        assumptions=(expiring, active, disputed),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        scenario_id="scenario-alpha",
        notes=("review assumptions before execution evidence",),
    )

    assert ledger.ledger_id.startswith("assumption-ledger-")
    assert ledger.schema_version == worldtwin.ASSUMPTION_SCHEMA_VERSION
    assert ledger.scenario_id == "scenario-alpha"
    assert ledger.lowest_confidence() == 0.42
    assert ledger.disputed_assumptions() == (disputed,)
    assert ledger.execution_blockers() == (active,)
    assert ledger.stale_assumptions_at(_created_at() + timedelta(hours=2)) == (expiring,)


def test_assumption_ledger_fingerprint_is_deterministic_for_reordered_inputs() -> None:
    first_assumption = worldtwin.create_assumption_record(
        name="First",
        category=worldtwin.AssumptionCategory.OPERATIONAL,
        statement="First assumption.",
        confidence=0.7,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.LOW,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
    )
    second_assumption = worldtwin.create_assumption_record(
        name="Second",
        category=worldtwin.AssumptionCategory.OPERATIONAL,
        statement="Second assumption.",
        confidence=0.8,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.MEDIUM,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
    )

    first_ledger = worldtwin.create_assumption_ledger(
        assumptions=(second_assumption, first_assumption),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        notes=("b", "a"),
    )
    second_ledger = worldtwin.create_assumption_ledger(
        assumptions=(first_assumption, second_assumption),
        created_at=_created_at(),
        owner="worldtwin-test-suite",
        notes=("a", "b"),
    )

    assert first_ledger.ledger_id == second_ledger.ledger_id
    assert first_ledger.fingerprint() == second_ledger.fingerprint()


def test_assumption_ledger_rejects_empty_or_duplicate_assumptions() -> None:
    with pytest.raises(ValueError, match="assumption ledger requires at least one assumption"):
        worldtwin.create_assumption_ledger(
            assumptions=(),
            created_at=_created_at(),
            owner="worldtwin-test-suite",
        )

    assumption = worldtwin.create_assumption_record(
        name="Duplicate",
        category=worldtwin.AssumptionCategory.OPERATIONAL,
        statement="Duplicate assumption.",
        confidence=0.7,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.LOW,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=_created_at(),
        owner="worldtwin-test-suite",
    )

    with pytest.raises(ValueError, match=f"duplicate assumption id: {assumption.assumption_id}"):
        worldtwin.create_assumption_ledger(
            assumptions=(assumption, assumption),
            created_at=_created_at(),
            owner="worldtwin-test-suite",
        )

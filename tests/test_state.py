from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_state_dimension_normalizes_and_validates_scalar_measurement() -> None:
    dimension = worldtwin.StateDimension(
        name=" temperature_c ",
        value=72,
        unit=" F ",
        description=" cabin sensor ",
        tags=(" thermal ", "sensor"),
    )

    assert dimension.name == "temperature_c"
    assert dimension.value == 72.0
    assert dimension.unit == "F"
    assert dimension.description == "cabin sensor"
    assert dimension.tags == ("thermal", "sensor")


def test_state_dimension_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="dimension value must be finite"):
        worldtwin.StateDimension(name="temperature", value=float("nan"), unit="F")


def test_observed_state_packet_records_bounded_observed_reality() -> None:
    valid_at = datetime(2026, 1, 1, 12, 1, tzinfo=UTC)
    state = worldtwin.create_observed_state(
        dimensions=(worldtwin.StateDimension("temperature", 72.5, "F"),),
        valid_at=valid_at,
        created_at=_created_at(),
        source="sensor-feed-alpha",
        notes=("baseline observation",),
    )

    assert state.kind is worldtwin.WorldStateKind.OBSERVED
    assert state.state_id.startswith("observed-state-")
    assert state.schema_version == worldtwin.STATE_SCHEMA_VERSION
    assert state.valid_at == valid_at
    assert state.created_at == _created_at()
    assert state.source == "sensor-feed-alpha"
    assert state.get_dimension("temperature").value == 72.5
    assert state.to_dimension_map() == {"temperature": 72.5}
    assert state.notes == ("baseline observation",)


def test_predicted_state_packet_supports_future_valid_time_and_lineage() -> None:
    created_at = _created_at()
    valid_at = created_at + timedelta(minutes=15)
    state = worldtwin.create_predicted_state(
        dimensions=(worldtwin.StateDimension("temperature", 76.0, "F"),),
        valid_at=valid_at,
        created_at=created_at,
        source="deterministic-drift-model",
        lineage=("observed-state-input",),
    )

    assert state.kind is worldtwin.WorldStateKind.PREDICTED
    assert state.state_id.startswith("predicted-state-")
    assert state.lineage == ("observed-state-input",)
    assert state.valid_at > state.created_at


def test_simulated_state_packet_supports_scenario_state_evolution() -> None:
    state = worldtwin.create_simulated_state(
        dimensions=(worldtwin.StateDimension("risk_score", 0.31, "score"),),
        valid_at=_created_at() + timedelta(minutes=5),
        created_at=_created_at(),
        source="scenario-branch-runner",
    )

    assert state.kind is worldtwin.WorldStateKind.SIMULATED
    assert state.state_id.startswith("simulated-state-")
    assert state.get_dimension("risk_score").value == 0.31


def test_world_state_rejects_duplicate_dimensions() -> None:
    dimensions = (
        worldtwin.StateDimension("temperature", 72.0, "F"),
        worldtwin.StateDimension("temperature", 73.0, "F"),
    )

    with pytest.raises(ValueError, match="duplicate state dimension: temperature"):
        worldtwin.create_observed_state(
            dimensions=dimensions,
            valid_at=_created_at(),
            created_at=_created_at(),
            source="sensor-feed-alpha",
        )


def test_world_state_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="state valid_at must be timezone-aware"):
        worldtwin.create_observed_state(
            dimensions=(worldtwin.StateDimension("temperature", 72.0, "F"),),
            valid_at=datetime(2026, 1, 1, 12, 0),
            created_at=_created_at(),
            source="sensor-feed-alpha",
        )


def test_world_state_normalizes_timezone_to_utc() -> None:
    pacific_like_time = datetime(2026, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=-8)))
    state = worldtwin.create_observed_state(
        dimensions=(worldtwin.StateDimension("temperature", 72.0, "F"),),
        valid_at=pacific_like_time,
        created_at=pacific_like_time,
        source="sensor-feed-alpha",
    )

    assert state.valid_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert state.created_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_world_state_fingerprint_is_deterministic_for_same_semantic_packet() -> None:
    created_at = _created_at()
    valid_at = created_at + timedelta(minutes=1)
    dimensions_a = (
        worldtwin.StateDimension("temperature", 72.0, "F"),
        worldtwin.StateDimension("humidity", 0.45, "ratio"),
    )
    dimensions_b = (
        worldtwin.StateDimension("humidity", 0.45, "ratio"),
        worldtwin.StateDimension("temperature", 72.0, "F"),
    )

    state_id_a = worldtwin.make_state_id(
        kind=worldtwin.WorldStateKind.OBSERVED,
        dimensions=dimensions_a,
        valid_at=valid_at,
        created_at=created_at,
        source="sensor-feed-alpha",
    )
    state_id_b = worldtwin.make_state_id(
        kind=worldtwin.WorldStateKind.OBSERVED,
        dimensions=dimensions_b,
        valid_at=valid_at,
        created_at=created_at,
        source="sensor-feed-alpha",
    )
    state_a = worldtwin.create_observed_state(
        dimensions=dimensions_a,
        valid_at=valid_at,
        created_at=created_at,
        source="sensor-feed-alpha",
        state_id=state_id_a,
    )
    state_b = worldtwin.create_observed_state(
        dimensions=dimensions_b,
        valid_at=valid_at,
        created_at=created_at,
        source="sensor-feed-alpha",
        state_id=state_id_b,
    )

    assert state_id_a == state_id_b
    assert state_a.fingerprint() == state_b.fingerprint()


def test_world_state_dimension_lookup_raises_for_missing_dimension() -> None:
    state = worldtwin.create_observed_state(
        dimensions=(worldtwin.StateDimension("temperature", 72.0, "F"),),
        valid_at=_created_at(),
        created_at=_created_at(),
        source="sensor-feed-alpha",
    )

    with pytest.raises(KeyError, match="state dimension not found: humidity"):
        state.get_dimension("humidity")

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_confidence_classifier_uses_conservative_tiers() -> None:
    assert worldtwin.classify_confidence(0.0) is worldtwin.ConfidenceTier.UNSUPPORTED
    assert worldtwin.classify_confidence(0.24) is worldtwin.ConfidenceTier.UNSUPPORTED
    assert worldtwin.classify_confidence(0.25) is worldtwin.ConfidenceTier.LOW
    assert worldtwin.classify_confidence(0.50) is worldtwin.ConfidenceTier.MODERATE
    assert worldtwin.classify_confidence(0.75) is worldtwin.ConfidenceTier.HIGH
    assert worldtwin.classify_confidence(0.90) is worldtwin.ConfidenceTier.BOUNDED_HIGH
    assert worldtwin.classify_confidence(1.0) is worldtwin.ConfidenceTier.BOUNDED_HIGH


def test_validate_confidence_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="confidence must be finite"):
        worldtwin.validate_confidence(float("nan"))

    with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
        worldtwin.validate_confidence(-0.01)

    with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
        worldtwin.validate_confidence(1.01)


def test_uncertainty_band_normalizes_and_reports_interval_math() -> None:
    band = worldtwin.UncertaintyBand(
        name=" temperature ",
        lower_bound=70,
        upper_bound=75,
        unit=" F ",
        confidence=0.8,
        source=worldtwin.UncertaintySource.MEASUREMENT_NOISE,
        rationale=" sensor tolerance ",
        tags=(" thermal ", "sensor"),
    )

    assert band.name == "temperature"
    assert band.lower_bound == 70.0
    assert band.upper_bound == 75.0
    assert band.unit == "F"
    assert band.confidence == 0.8
    assert band.rationale == "sensor tolerance"
    assert band.tags == ("thermal", "sensor")
    assert band.width() == 5.0
    assert band.midpoint() == 72.5
    assert band.contains(72.5) is True
    assert band.contains(80.0) is False


def test_uncertainty_band_rejects_inverted_bounds() -> None:
    with pytest.raises(
        ValueError,
        match="uncertainty lower bound must be less than or equal to upper bound",
    ):
        worldtwin.UncertaintyBand(
            name="temperature",
            lower_bound=80,
            upper_bound=70,
            unit="F",
            confidence=0.8,
            source=worldtwin.UncertaintySource.MODEL_ERROR,
            rationale="bad interval",
        )


def test_confidence_assessment_computes_tier_and_stable_id() -> None:
    band = worldtwin.UncertaintyBand(
        name="temperature",
        lower_bound=70,
        upper_bound=75,
        unit="F",
        confidence=0.8,
        source=worldtwin.UncertaintySource.MEASUREMENT_NOISE,
        rationale="sensor tolerance",
    )
    assessment = worldtwin.create_confidence_assessment(
        target_id="prediction-001",
        confidence=0.72,
        rationale="Prediction is bounded by available telemetry and assumptions.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
        evidence_ids=(" evidence-b ", "evidence-a"),
        uncertainty_bands=(band,),
    )

    assert assessment.assessment_id.startswith("confidence-assessment-")
    assert assessment.target_id == "prediction-001"
    assert assessment.confidence == 0.72
    assert assessment.tier is worldtwin.ConfidenceTier.MODERATE
    assert assessment.created_at == _created_at()
    assert assessment.assessor == "worldtwin-confidence-gate"
    assert assessment.evidence_ids == ("evidence-a", "evidence-b")
    assert assessment.uncertainty_bands == (band,)
    assert assessment.schema_version == worldtwin.UNCERTAINTY_SCHEMA_VERSION


def test_confidence_assessment_rejects_tier_mismatch_when_constructed_directly() -> None:
    with pytest.raises(
        ValueError,
        match="confidence assessment tier must match the normalized confidence value",
    ):
        worldtwin.ConfidenceAssessment(
            assessment_id="confidence-assessment-manual",
            target_id="prediction-001",
            confidence=0.10,
            tier=worldtwin.ConfidenceTier.HIGH,
            rationale="This direct construction is intentionally inconsistent.",
            created_at=_created_at(),
            assessor="manual-test",
        )


def test_confidence_assessment_rejects_naive_created_at() -> None:
    with pytest.raises(
        ValueError,
        match="confidence assessment created_at must be timezone-aware",
    ):
        worldtwin.create_confidence_assessment(
            target_id="prediction-001",
            confidence=0.72,
            rationale="Prediction is bounded by available telemetry and assumptions.",
            created_at=datetime(2026, 1, 1, 12, 0),
            assessor="worldtwin-confidence-gate",
        )


def test_confidence_assessment_normalizes_timezone_to_utc() -> None:
    local_time = datetime(2026, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=-8)))
    assessment = worldtwin.create_confidence_assessment(
        target_id="prediction-001",
        confidence=0.72,
        rationale="Prediction is bounded by available telemetry and assumptions.",
        created_at=local_time,
        assessor="worldtwin-confidence-gate",
    )

    assert assessment.created_at == _created_at()


def test_confidence_assessment_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValueError, match="duplicate evidence id"):
        worldtwin.create_confidence_assessment(
            target_id="prediction-001",
            confidence=0.72,
            rationale="Prediction is bounded by available telemetry and assumptions.",
            created_at=_created_at(),
            assessor="worldtwin-confidence-gate",
            evidence_ids=("evidence-a", "evidence-a"),
        )


def test_confidence_assessment_rejects_duplicate_uncertainty_band_names() -> None:
    first = worldtwin.UncertaintyBand(
        name="temperature",
        lower_bound=70,
        upper_bound=75,
        unit="F",
        confidence=0.8,
        source=worldtwin.UncertaintySource.MEASUREMENT_NOISE,
        rationale="sensor tolerance",
    )
    second = worldtwin.UncertaintyBand(
        name="temperature",
        lower_bound=69,
        upper_bound=76,
        unit="F",
        confidence=0.7,
        source=worldtwin.UncertaintySource.MODEL_ERROR,
        rationale="model residual",
    )

    with pytest.raises(ValueError, match="duplicate uncertainty band: temperature"):
        worldtwin.create_confidence_assessment(
            target_id="prediction-001",
            confidence=0.72,
            rationale="Prediction is bounded by available telemetry and assumptions.",
            created_at=_created_at(),
            assessor="worldtwin-confidence-gate",
            uncertainty_bands=(first, second),
        )


def test_confidence_assessment_fingerprint_is_deterministic() -> None:
    first = worldtwin.create_confidence_assessment(
        target_id="prediction-001",
        confidence=0.72,
        rationale="Prediction is bounded by available telemetry and assumptions.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
        evidence_ids=("b", "a"),
    )
    second = worldtwin.create_confidence_assessment(
        target_id="prediction-001",
        confidence=0.72,
        rationale="Prediction is bounded by available telemetry and assumptions.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
        evidence_ids=("a", "b"),
    )

    assert first.assessment_id == second.assessment_id
    assert first.fingerprint() == second.fingerprint()


def test_combine_confidence_conservatively_uses_lowest_valid_value() -> None:
    assert worldtwin.combine_confidence_conservatively((0.91, 0.64, 0.82)) == 0.64

    with pytest.raises(ValueError, match="at least one confidence value is required"):
        worldtwin.combine_confidence_conservatively(())

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _simulation() -> worldtwin.SimulationResult:
    return worldtwin.run_deterministic_simulation(
        scenario=worldtwin.build_thermal_drift_scenario(),
        rules=(
            worldtwin.create_simulation_rule(
                target="temperature",
                delta_per_step=3.0,
                unit="F",
                description="Simple deterministic thermal drift.",
                minimum=-40.0,
                maximum=220.0,
            ),
            worldtwin.create_simulation_rule(
                target="risk_score",
                delta_per_step=0.10,
                unit="score",
                description="Simple deterministic risk accumulation.",
                initial_value=0.0,
                minimum=0.0,
                maximum=1.0,
                clamp_to_bounds=True,
            ),
        ),
        config=worldtwin.SimulationConfig(
            step_count=5,
            step_seconds=60,
            created_at=_created_at(),
        ),
    )


def _prediction() -> worldtwin.PredictionResult:
    simulation = _simulation()
    confidence = worldtwin.create_confidence_assessment(
        target_id=simulation.simulation_id,
        confidence=0.80,
        rationale="Simulation is deterministic and scenario-bounded.",
        created_at=_created_at(),
        assessor="worldtwin-confidence-gate",
    )
    return worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=_created_at(),
        created_by="worldtwin-prediction-gate",
        confidence_assessment=confidence,
    )


def _observed_state(
    *,
    temperature: float = 87.5,
    risk_score: float = 0.55,
) -> worldtwin.WorldState:
    prediction = _prediction()
    return worldtwin.create_observed_state(
        dimensions=(
            worldtwin.StateDimension(
                name="temperature",
                value=temperature,
                unit="F",
                description="Observed final temperature.",
            ),
            worldtwin.StateDimension(
                name="risk_score",
                value=risk_score,
                unit="score",
                description="Observed final risk score.",
            ),
        ),
        valid_at=prediction.final_state.valid_at + timedelta(minutes=1),
        created_at=_created_at(),
        source="reality-observation-alpha",
        lineage=(prediction.final_state.state_id,),
    )


def test_dimension_delta_classifies_clean_match() -> None:
    delta = worldtwin.create_dimension_delta(
        name="temperature",
        predicted_value=87.0,
        observed_value=87.5,
        tolerance=2.0,
        unit="F",
    )

    assert delta.name == "temperature"
    assert delta.predicted_value == 87.0
    assert delta.observed_value == 87.5
    assert delta.absolute_error == 0.5
    assert delta.tolerance == 2.0
    assert delta.normalized_error == 0.25
    assert delta.severity is worldtwin.RealityDeltaSeverity.INFO
    assert delta.passed is True
    assert delta.schema_version == worldtwin.REALITY_DELTA_SCHEMA_VERSION


def test_reality_delta_severity_thresholds_are_conservative() -> None:
    assert worldtwin.classify_reality_delta_severity(0.0) is (
        worldtwin.RealityDeltaSeverity.INFO
    )
    assert worldtwin.classify_reality_delta_severity(1.0) is (
        worldtwin.RealityDeltaSeverity.INFO
    )
    assert worldtwin.classify_reality_delta_severity(1.01) is (
        worldtwin.RealityDeltaSeverity.WARNING
    )
    assert worldtwin.classify_reality_delta_severity(2.0) is (
        worldtwin.RealityDeltaSeverity.ERROR
    )
    assert worldtwin.classify_reality_delta_severity(5.0) is (
        worldtwin.RealityDeltaSeverity.CRITICAL
    )


def test_reality_delta_report_matches_clean_prediction_to_observation() -> None:
    prediction = _prediction()
    report = worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=_observed_state(),
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
        notes=("post-run accountability check",),
    )

    assert report.report_id.startswith("reality-delta-")
    assert report.prediction_id == prediction.prediction_id
    assert report.scenario_id == prediction.scenario_id
    assert report.predicted_state_id == prediction.final_state.state_id
    assert report.observed_state_id.startswith("observed-state-")
    assert report.verdict is worldtwin.RealityDeltaVerdict.MATCH
    assert report.passed is True
    assert report.blocks_trust_increase is False
    assert report.highest_delta_severity() is worldtwin.RealityDeltaSeverity.INFO
    assert report.failed_deltas() == ()
    assert report.notes == ("post-run accountability check",)
    assert report.delta_table() == {"risk_score": 0.5000000000000004, "temperature": 0.25}


def test_reality_delta_report_detects_warning_drift() -> None:
    report = worldtwin.create_reality_delta_report(
        prediction=_prediction(),
        observed_state=_observed_state(temperature=90.0, risk_score=0.55),
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )

    assert report.verdict is worldtwin.RealityDeltaVerdict.DRIFT
    assert report.highest_delta_severity() is worldtwin.RealityDeltaSeverity.WARNING
    assert tuple(delta.name for delta in report.failed_deltas()) == ("temperature",)


def test_reality_delta_report_detects_error_breach() -> None:
    report = worldtwin.create_reality_delta_report(
        prediction=_prediction(),
        observed_state=_observed_state(temperature=92.0, risk_score=0.55),
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )

    assert report.verdict is worldtwin.RealityDeltaVerdict.BREACH
    assert report.blocks_trust_increase is True
    assert report.highest_delta_severity() is worldtwin.RealityDeltaSeverity.ERROR


def test_reality_delta_report_quarantines_critical_error() -> None:
    report = worldtwin.create_reality_delta_report(
        prediction=_prediction(),
        observed_state=_observed_state(temperature=99.0, risk_score=0.55),
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )

    assert report.verdict is worldtwin.RealityDeltaVerdict.QUARANTINE
    assert report.blocks_trust_increase is True
    assert report.highest_delta_severity() is worldtwin.RealityDeltaSeverity.CRITICAL


def test_reality_delta_report_quarantines_missing_observed_dimension() -> None:
    prediction = _prediction()
    observed_state = worldtwin.create_observed_state(
        dimensions=(
            worldtwin.StateDimension(
                name="temperature",
                value=87.5,
                unit="F",
                description="Observed final temperature.",
            ),
        ),
        valid_at=prediction.final_state.valid_at + timedelta(minutes=1),
        created_at=_created_at(),
        source="reality-observation-alpha",
    )

    report = worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=observed_state,
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )

    assert report.verdict is worldtwin.RealityDeltaVerdict.QUARANTINE
    assert report.missing_observed_dimensions == ("risk_score",)
    assert report.highest_delta_severity() is worldtwin.RealityDeltaSeverity.CRITICAL


def test_reality_delta_report_rejects_missing_predicted_dimension() -> None:
    prediction = _prediction()

    report = worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=_observed_state(),
        tolerances={"unknown_dimension": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )

    assert report.verdict is worldtwin.RealityDeltaVerdict.QUARANTINE
    assert report.missing_predicted_dimensions == ("unknown_dimension",)
    assert report.missing_observed_dimensions == ("unknown_dimension",)


def test_reality_delta_report_ignores_unscored_extra_state_dimensions() -> None:
    prediction = _prediction()
    report = worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=_observed_state(),
        tolerances={"temperature": 2.0},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )

    assert "load" in prediction.final_values
    assert report.verdict is worldtwin.RealityDeltaVerdict.MATCH
    assert report.missing_observed_dimensions == ()
    assert report.delta_table() == {"temperature": 0.25}


def test_reality_delta_report_rejects_non_observed_reality_state() -> None:
    prediction = _prediction()

    with pytest.raises(ValueError, match="reality-delta observed_state must be observed reality"):
        worldtwin.create_reality_delta_report(
            prediction=prediction,
            observed_state=prediction.final_state,
            tolerances={"temperature": 2.0, "risk_score": 0.10},
            created_at=_created_at(),
            created_by="worldtwin-delta-gate",
        )


def test_reality_delta_report_fingerprint_is_replay_stable() -> None:
    prediction = _prediction()
    observed_state = _observed_state()

    first = worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=observed_state,
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
        notes=("b", "a"),
    )
    second = worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=observed_state,
        tolerances={"risk_score": 0.10, "temperature": 2.0},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
        notes=("a", "b"),
    )

    assert first.report_id == second.report_id
    assert first.fingerprint() == second.fingerprint()


def test_reality_delta_report_rejects_verdict_mismatch_when_constructed_directly() -> None:
    prediction = _prediction()
    observed_state = _observed_state()
    delta = worldtwin.create_dimension_delta(
        name="temperature",
        predicted_value=87.0,
        observed_value=99.0,
        tolerance=2.0,
        unit="F",
    )

    with pytest.raises(
        ValueError,
        match="reality-delta verdict must match delta and missing-dimension state",
    ):
        worldtwin.RealityDeltaReport(
            report_id="reality-delta-manual",
            prediction_id=prediction.prediction_id,
            scenario_id=prediction.scenario_id,
            predicted_state_id=prediction.final_state.state_id,
            observed_state_id=observed_state.state_id,
            created_at=_created_at(),
            created_by="worldtwin-delta-gate",
            verdict=worldtwin.RealityDeltaVerdict.MATCH,
            deltas=(delta,),
        )

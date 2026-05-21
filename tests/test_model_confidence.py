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


def _delta_report(
    *,
    temperature: float = 87.5,
    risk_score: float = 0.55,
) -> worldtwin.RealityDeltaReport:
    return worldtwin.create_reality_delta_report(
        prediction=_prediction(),
        observed_state=_observed_state(
            temperature=temperature,
            risk_score=risk_score,
        ),
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=_created_at(),
        created_by="worldtwin-delta-gate",
    )


def test_model_confidence_observation_normalizes_and_classifies_delta() -> None:
    observation = worldtwin.create_model_confidence_observation(
        model_id=" deterministic-kernel-v1 ",
        source_kind=worldtwin.ModelConfidenceSourceKind.HUMAN_REVIEW,
        source_id=" review-alpha ",
        score_delta=0.10,
        rationale=" Reviewer accepted the evidence package. ",
        created_at=_created_at(),
        created_by=" worldtwin-reviewer ",
        tags=(" review ", "human"),
    )

    assert observation.observation_id.startswith("model-confidence-observation-")
    assert observation.schema_version == worldtwin.MODEL_CONFIDENCE_SCHEMA_VERSION
    assert observation.model_id == "deterministic-kernel-v1"
    assert observation.source_id == "review-alpha"
    assert observation.score_delta == 0.10
    assert observation.rationale == "Reviewer accepted the evidence package."
    assert observation.created_by == "worldtwin-reviewer"
    assert observation.tags == ("human", "review")
    assert observation.is_positive is True
    assert observation.is_negative is False


def test_model_confidence_profile_scores_base_plus_observations() -> None:
    positive = worldtwin.create_model_confidence_observation(
        model_id="deterministic-kernel-v1",
        source_kind=worldtwin.ModelConfidenceSourceKind.HUMAN_REVIEW,
        source_id="review-alpha",
        score_delta=0.20,
        rationale="Reviewer accepted the evidence package.",
        created_at=_created_at(),
        created_by="worldtwin-reviewer",
    )
    negative = worldtwin.create_model_confidence_observation(
        model_id="deterministic-kernel-v1",
        source_kind=worldtwin.ModelConfidenceSourceKind.POLICY_EVALUATION,
        source_id="policy-alpha",
        score_delta=-0.10,
        rationale="Policy produced caution.",
        created_at=_created_at() + timedelta(minutes=1),
        created_by="worldtwin-policy-gate",
    )
    profile = worldtwin.create_model_confidence_profile(
        model_id="deterministic-kernel-v1",
        base_confidence=0.50,
        observations=(negative, positive),
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
        notes=("initial model tracking",),
    )

    assert profile.profile_id.startswith("model-confidence-profile-")
    assert profile.confidence_score == 0.60
    assert profile.trust_tier is worldtwin.ModelTrustTier.CANDIDATE
    assert profile.net_observation_delta() == 0.1
    assert profile.positive_observations() == (positive,)
    assert profile.negative_observations() == (negative,)
    assert profile.allows_adaptation_review is True
    assert profile.blocks_trust_increase is False
    assert profile.notes == ("initial model tracking",)


def test_reality_delta_match_increases_model_confidence_slightly() -> None:
    report = _delta_report()
    observation = worldtwin.create_reality_delta_confidence_observation(
        model_id="deterministic-kernel-v1",
        report=report,
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
    )

    assert report.verdict is worldtwin.RealityDeltaVerdict.MATCH
    assert observation.source_kind is worldtwin.ModelConfidenceSourceKind.REALITY_DELTA
    assert observation.source_id == report.report_id
    assert observation.score_delta == 0.05
    assert observation.tags == ("match", "reality-delta")


def test_reality_delta_breach_decreases_model_confidence() -> None:
    report = _delta_report(temperature=92.0)
    observation = worldtwin.create_reality_delta_confidence_observation(
        model_id="deterministic-kernel-v1",
        report=report,
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
    )

    assert report.verdict is worldtwin.RealityDeltaVerdict.BREACH
    assert observation.score_delta == -0.25
    assert observation.is_negative is True


def test_update_model_confidence_from_reality_delta_can_suspend_trust() -> None:
    clean_report = _delta_report()
    bad_report = _delta_report(temperature=99.0)
    clean_observation = worldtwin.create_reality_delta_confidence_observation(
        model_id="deterministic-kernel-v1",
        report=clean_report,
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
    )
    profile = worldtwin.create_model_confidence_profile(
        model_id="deterministic-kernel-v1",
        base_confidence=0.50,
        observations=(clean_observation,),
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
    )

    updated = worldtwin.update_model_confidence_from_reality_delta(
        profile=profile,
        report=bad_report,
        created_at=_created_at() + timedelta(minutes=1),
        created_by="worldtwin-confidence-ledger",
    )

    assert bad_report.verdict is worldtwin.RealityDeltaVerdict.QUARANTINE
    assert profile.confidence_score == 0.55
    assert updated.confidence_score == pytest.approx(0.05)
    assert updated.trust_tier is worldtwin.ModelTrustTier.SUSPENDED
    assert updated.blocks_trust_increase is True
    assert updated.allows_adaptation_review is False
    assert len(updated.observations) == 2


def test_model_trust_tier_thresholds_are_conservative() -> None:
    assert worldtwin.classify_model_trust_tier(0.00) is worldtwin.ModelTrustTier.SUSPENDED
    assert worldtwin.classify_model_trust_tier(0.10) is worldtwin.ModelTrustTier.UNTRUSTED
    assert worldtwin.classify_model_trust_tier(0.35) is worldtwin.ModelTrustTier.WATCHLIST
    assert worldtwin.classify_model_trust_tier(0.60) is worldtwin.ModelTrustTier.CANDIDATE
    assert worldtwin.classify_model_trust_tier(0.85) is worldtwin.ModelTrustTier.TRUSTED


def test_model_confidence_profile_fingerprint_is_replay_stable() -> None:
    observation = worldtwin.create_model_confidence_observation(
        model_id="deterministic-kernel-v1",
        source_kind=worldtwin.ModelConfidenceSourceKind.HUMAN_REVIEW,
        source_id="review-alpha",
        score_delta=0.20,
        rationale="Reviewer accepted the evidence package.",
        created_at=_created_at(),
        created_by="worldtwin-reviewer",
    )

    first = worldtwin.create_model_confidence_profile(
        model_id="deterministic-kernel-v1",
        base_confidence=0.50,
        observations=(observation,),
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
        notes=("b", "a"),
    )
    second = worldtwin.create_model_confidence_profile(
        model_id="deterministic-kernel-v1",
        base_confidence=0.50,
        observations=(observation,),
        created_at=_created_at(),
        created_by="worldtwin-confidence-ledger",
        notes=("a", "b"),
    )

    assert first.profile_id == second.profile_id
    assert first.fingerprint() == second.fingerprint()


def test_model_confidence_rejects_duplicate_observations() -> None:
    observation = worldtwin.create_model_confidence_observation(
        model_id="deterministic-kernel-v1",
        source_kind=worldtwin.ModelConfidenceSourceKind.HUMAN_REVIEW,
        source_id="review-alpha",
        score_delta=0.20,
        rationale="Reviewer accepted the evidence package.",
        created_at=_created_at(),
        created_by="worldtwin-reviewer",
    )

    with pytest.raises(ValueError, match="duplicate model-confidence observation"):
        worldtwin.create_model_confidence_profile(
            model_id="deterministic-kernel-v1",
            base_confidence=0.50,
            observations=(observation, observation),
            created_at=_created_at(),
            created_by="worldtwin-confidence-ledger",
        )


def test_model_confidence_profile_rejects_mismatched_direct_score() -> None:
    with pytest.raises(
        ValueError,
        match="model confidence_score must match base confidence and observations",
    ):
        worldtwin.ModelConfidenceProfile(
            profile_id="model-confidence-profile-manual",
            model_id="deterministic-kernel-v1",
            base_confidence=0.50,
            confidence_score=0.90,
            trust_tier=worldtwin.ModelTrustTier.TRUSTED,
            observations=(),
            created_at=_created_at(),
            created_by="worldtwin-confidence-ledger",
        )


def test_model_confidence_observation_rejects_out_of_range_delta() -> None:
    with pytest.raises(ValueError, match=r"score delta must be between -1\.0 and 1\.0"):
        worldtwin.create_model_confidence_observation(
            model_id="deterministic-kernel-v1",
            source_kind=worldtwin.ModelConfidenceSourceKind.MANUAL_ADJUSTMENT,
            source_id="manual-alpha",
            score_delta=1.5,
            rationale="Invalid adjustment.",
            created_at=_created_at(),
            created_by="worldtwin-confidence-ledger",
        )

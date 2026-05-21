from __future__ import annotations

from datetime import UTC, datetime

import pytest

import ix_blackfox_worldtwin as worldtwin


def _created_at() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _config() -> worldtwin.SimulationConfig:
    return worldtwin.SimulationConfig(
        step_count=5,
        step_seconds=60,
        created_at=_created_at(),
        tags=("risk", "ci-safe"),
    )


def _branch(
    *,
    name: str,
    temperature_delta: float,
    risk_delta: float,
) -> worldtwin.BranchDefinition:
    return worldtwin.create_branch_definition(
        name=name,
        description=f"Risk branch for {name}.",
        rules=(
            worldtwin.create_simulation_rule(
                target="temperature",
                delta_per_step=temperature_delta,
                unit="F",
                description="Deterministic thermal drift.",
                minimum=-40.0,
                maximum=220.0,
            ),
            worldtwin.create_simulation_rule(
                target="risk_score",
                delta_per_step=risk_delta,
                unit="score",
                description="Deterministic risk accumulation.",
                initial_value=0.0,
                minimum=0.0,
                maximum=1.0,
                clamp_to_bounds=True,
            ),
        ),
        config=_config(),
        tags=("risk",),
    )


def _comparison() -> worldtwin.BranchComparison:
    scenario = worldtwin.build_thermal_drift_scenario()
    low = _branch(name="Low risk", temperature_delta=1.0, risk_delta=0.05)
    high = _branch(name="High risk", temperature_delta=5.0, risk_delta=0.18)

    return worldtwin.run_branching_simulation(
        scenario=scenario,
        branches=(low, high),
        ranking_target="risk_score",
        ranking_direction=worldtwin.BranchRankingDirection.DESCENDING,
        created_at=_created_at(),
        created_by="worldtwin-test-suite",
    )


def test_risk_factor_normalizes_observed_value_and_weight() -> None:
    factor = worldtwin.create_risk_factor(
        target="risk_score",
        observed_value=0.75,
        weight=2.0,
        rationale="Risk score is already normalized.",
        tags=("risk", "branch"),
    )

    assert factor.factor_id.startswith("risk-factor-")
    assert factor.schema_version == worldtwin.RISK_SCHEMA_VERSION
    assert factor.target == "risk_score"
    assert factor.observed_value == 0.75
    assert factor.normalized_value == 0.75
    assert factor.weight == 2.0
    assert factor.weighted_contribution == 1.5
    assert factor.severity is worldtwin.RiskSeverity.ERROR
    assert factor.tags == ("branch", "risk")


def test_risk_factor_clamps_non_normalized_observed_values() -> None:
    high = worldtwin.create_risk_factor(
        target="temperature",
        observed_value=120.0,
        weight=1.0,
        rationale="Raw non-normalized value clamps to maximum risk.",
    )
    low = worldtwin.create_risk_factor(
        target="negative",
        observed_value=-10.0,
        weight=1.0,
        rationale="Negative raw value clamps to zero risk.",
    )

    assert high.normalized_value == 1.0
    assert high.severity is worldtwin.RiskSeverity.CRITICAL
    assert low.normalized_value == 0.0
    assert low.severity is worldtwin.RiskSeverity.INFO


def test_classify_risk_severity_and_recommendation() -> None:
    assert worldtwin.classify_risk_severity(score=0.10) is worldtwin.RiskSeverity.INFO
    assert worldtwin.classify_risk_severity(score=0.40) is worldtwin.RiskSeverity.WARNING
    assert worldtwin.classify_risk_severity(score=0.70) is worldtwin.RiskSeverity.ERROR
    assert worldtwin.classify_risk_severity(score=0.90) is worldtwin.RiskSeverity.CRITICAL

    assert worldtwin.classify_risk_recommendation(score=0.10) is (
        worldtwin.RiskRecommendation.ACCEPT
    )
    assert worldtwin.classify_risk_recommendation(score=0.40) is (
        worldtwin.RiskRecommendation.CAUTION
    )
    assert worldtwin.classify_risk_recommendation(score=0.70) is (
        worldtwin.RiskRecommendation.DENY
    )
    assert worldtwin.classify_risk_recommendation(score=0.90) is (
        worldtwin.RiskRecommendation.QUARANTINE
    )


def test_score_branch_risk_profiles_one_branch() -> None:
    comparison = _comparison()
    low_result = comparison.trailing_result()

    profile = worldtwin.score_branch_risk(
        result=low_result,
        target_weights={"risk_score": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )

    assert profile.profile_id.startswith("risk-profile-")
    assert profile.scenario_id == comparison.scenario_id
    assert profile.branch_id == low_result.branch_id
    assert profile.simulation_id == low_result.simulation.simulation_id
    assert profile.aggregate_score == 0.25
    assert profile.severity is worldtwin.RiskSeverity.INFO
    assert profile.recommendation is worldtwin.RiskRecommendation.ACCEPT
    assert profile.blocks_execution_review is False
    assert profile.requires_human_caution is False
    assert profile.factor_targets() == ("risk_score",)


def test_score_branch_risk_denies_high_risk_branch() -> None:
    comparison = _comparison()
    high_result = comparison.leading_result()

    profile = worldtwin.score_branch_risk(
        result=high_result,
        target_weights={"risk_score": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )

    assert profile.aggregate_score == 0.9
    assert profile.severity is worldtwin.RiskSeverity.CRITICAL
    assert profile.recommendation is worldtwin.RiskRecommendation.QUARANTINE
    assert profile.blocks_execution_review is True


def test_compare_branch_risks_ranks_highest_risk_profile() -> None:
    comparison = _comparison()
    risk_comparison = worldtwin.compare_branch_risks(
        comparison=comparison,
        target_weights={"risk_score": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )

    assert risk_comparison.comparison_id.startswith("risk-comparison-")
    assert risk_comparison.scenario_id == comparison.scenario_id
    assert len(risk_comparison.profiles) == 2
    assert risk_comparison.highest_risk_profile().aggregate_score == 0.9
    assert risk_comparison.lowest_risk_profile().aggregate_score == 0.25
    assert risk_comparison.branch_score_table() == {
        risk_comparison.highest_risk_profile().branch_id: 0.9,
        risk_comparison.lowest_risk_profile().branch_id: 0.25,
    }


def test_risk_comparison_fingerprint_is_replay_stable() -> None:
    comparison = _comparison()
    first = worldtwin.compare_branch_risks(
        comparison=comparison,
        target_weights={"risk_score": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )
    second = worldtwin.compare_branch_risks(
        comparison=comparison,
        target_weights={"risk_score": 1.0},
        created_at=_created_at(),
        created_by="worldtwin-risk-gate",
    )

    assert first.comparison_id == second.comparison_id
    assert first.fingerprint() == second.fingerprint()


def test_risk_scoring_rejects_missing_weights() -> None:
    with pytest.raises(ValueError, match="risk scoring requires at least one target weight"):
        worldtwin.score_branch_risk(
            result=_comparison().leading_result(),
            target_weights={},
            created_at=_created_at(),
            created_by="worldtwin-risk-gate",
        )


def test_risk_scoring_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValueError, match="risk thresholds must satisfy caution < deny < quarantine"):
        worldtwin.score_branch_risk(
            result=_comparison().leading_result(),
            target_weights={"risk_score": 1.0},
            created_at=_created_at(),
            created_by="worldtwin-risk-gate",
            caution_threshold=0.80,
            deny_threshold=0.70,
            quarantine_threshold=0.90,
        )


def test_risk_scoring_rejects_unknown_target() -> None:
    with pytest.raises(KeyError, match="branch final target not found: unknown"):
        worldtwin.score_branch_risk(
            result=_comparison().leading_result(),
            target_weights={"unknown": 1.0},
            created_at=_created_at(),
            created_by="worldtwin-risk-gate",
        )


def test_risk_profile_rejects_empty_factors_when_constructed_directly() -> None:
    with pytest.raises(ValueError, match="risk profile requires at least one factor"):
        worldtwin.RiskProfile(
            profile_id="risk-profile-manual",
            scenario_id="scenario-alpha",
            branch_id="branch-alpha",
            simulation_id="simulation-alpha",
            aggregate_score=0.1,
            severity=worldtwin.RiskSeverity.INFO,
            recommendation=worldtwin.RiskRecommendation.ACCEPT,
            factors=(),
            created_at=_created_at(),
            created_by="worldtwin-risk-gate",
        )

"""Command-line entry points for IX-BlackFox-WorldTwin.

The CLI is intentionally small and deterministic. It gives reviewers a runnable
Wave 1 path that creates a complete evidence package without requiring network
access, external services, GPUs, or unsafe execution privileges.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import NoReturn, Sequence

import ix_blackfox_worldtwin as worldtwin

DEMO_MODEL_ID = "deterministic-kernel-v1"
DEMO_CREATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the IX-BlackFox-WorldTwin CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-demo":
        bundle = build_demo_review_bundle()
        output = bundle.to_json()
        if args.pretty:
            output = json.dumps(json.loads(output), indent=2, sort_keys=True)
        print(output)
        return 0

    _unreachable_command(args.command)


def build_demo_review_bundle() -> worldtwin.ReviewBundle:
    """Build a complete deterministic Wave 1 review bundle."""

    scenario = worldtwin.build_thermal_drift_scenario()
    simulation = worldtwin.run_deterministic_simulation(
        scenario=scenario,
        rules=_simulation_rules(),
        config=worldtwin.SimulationConfig(
            step_count=5,
            step_seconds=60,
            created_at=DEMO_CREATED_AT,
            tags=("cli-demo", "deterministic"),
        ),
    )
    confidence = worldtwin.create_confidence_assessment(
        target_id=simulation.simulation_id,
        confidence=0.90,
        rationale="CLI demo uses a deterministic, bounded simulation path.",
        created_at=DEMO_CREATED_AT,
        assessor="worldtwin-cli",
    )
    manifest = worldtwin.create_reproducibility_manifest(
        scenario=scenario,
        simulation=simulation,
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
        notes=("cli-demo-replayable",),
    )
    prediction = worldtwin.create_prediction_result(
        simulation=simulation,
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
        confidence_assessment=confidence,
        reproducibility_manifest=manifest,
    )
    receipt = worldtwin.create_prediction_receipt(
        prediction=prediction,
        reproducibility_manifest=manifest,
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
    )
    chain = worldtwin.create_receipt_chain(
        receipts=(receipt,),
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
        notes=("cli-demo-chain",),
    )
    chain_validation = worldtwin.validate_receipt_chain(
        chain=chain,
        receipts=(receipt,),
        checked_at=DEMO_CREATED_AT,
        checked_by="worldtwin-cli",
    )
    policy = _policy_allow(scenario=scenario, simulation=simulation)
    delta_report = worldtwin.create_reality_delta_report(
        prediction=prediction,
        observed_state=_observed_state(prediction),
        tolerances={"temperature": 2.0, "risk_score": 0.10},
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
        notes=("cli-demo-accountability",),
    )
    confidence_profile = worldtwin.create_model_confidence_profile(
        model_id=DEMO_MODEL_ID,
        base_confidence=0.90,
        observations=(
            worldtwin.create_reality_delta_confidence_observation(
                model_id=DEMO_MODEL_ID,
                report=delta_report,
                created_at=DEMO_CREATED_AT,
                created_by="worldtwin-cli",
            ),
        ),
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
        notes=("cli-demo-confidence",),
    )
    candidate = worldtwin.create_adaptation_candidate(
        model_id=DEMO_MODEL_ID,
        scope=worldtwin.AdaptationScope.SIMULATION_RULE,
        target_artifact_id=prediction.prediction_id,
        summary="Review deterministic thermal drift rule after clean demo evidence.",
        proposed_change_fingerprint="sha256:cli-demo-adaptation-change",
        created_at=DEMO_CREATED_AT,
        proposed_by="worldtwin-cli",
        evidence_ids=(delta_report.report_id, receipt.receipt_id),
        tags=("cli-demo", "review-only"),
    )
    adaptation_gate = worldtwin.evaluate_adaptation_gate(
        candidate=candidate,
        confidence_profile=confidence_profile,
        reality_delta_report=delta_report,
        receipt_chain_validation=chain_validation,
        policy_evaluation=policy,
        created_at=DEMO_CREATED_AT,
        evaluated_by="worldtwin-cli",
    )
    handoff = worldtwin.create_handoff_package(
        target=worldtwin.HandoffTarget.BLACKFOX_EXECUTION_GOVERNANCE,
        prediction=prediction,
        receipt=receipt,
        receipt_chain=chain,
        receipt_chain_validation=chain_validation,
        policy_evaluation=policy,
        adaptation_gate_result=adaptation_gate,
        reality_delta_report=delta_report,
        model_confidence_profile=confidence_profile,
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
        requested_action="Queue deterministic WorldTwin evidence for human review.",
        notes=("cli-demo-human-review-only",),
    )
    bundle = worldtwin.create_review_bundle(
        handoff=handoff,
        created_at=DEMO_CREATED_AT,
        created_by="worldtwin-cli",
    )
    validation = worldtwin.validate_review_bundle(
        bundle=bundle,
        checked_at=DEMO_CREATED_AT,
        checked_by="worldtwin-cli",
    )

    if not validation.passed:
        joined_issues = ", ".join(validation.issues)
        raise RuntimeError(f"demo review bundle failed validation: {joined_issues}")

    return bundle


def _simulation_rules() -> tuple[worldtwin.SimulationRule, ...]:
    return (
        worldtwin.create_simulation_rule(
            target="temperature",
            delta_per_step=3.0,
            unit="F",
            description="CLI demo deterministic thermal drift.",
            minimum=-40.0,
            maximum=220.0,
            tags=("cli-demo", "thermal"),
        ),
        worldtwin.create_simulation_rule(
            target="risk_score",
            delta_per_step=0.10,
            unit="score",
            description="CLI demo deterministic risk accumulation.",
            initial_value=0.0,
            minimum=0.0,
            maximum=1.0,
            clamp_to_bounds=True,
            tags=("cli-demo", "risk"),
        ),
    )


def _policy_allow(
    *,
    scenario: worldtwin.ScenarioManifest,
    simulation: worldtwin.SimulationResult,
) -> worldtwin.PolicyEvaluation:
    assumption = worldtwin.create_assumption_record(
        name="Telemetry source is authenticated",
        category=worldtwin.AssumptionCategory.DATA_QUALITY,
        statement="The telemetry source identity is authenticated for the CLI demo.",
        confidence=0.85,
        impact_if_wrong=worldtwin.AssumptionImpactLevel.HIGH,
        status=worldtwin.AssumptionStatus.ACTIVE,
        created_at=DEMO_CREATED_AT,
        owner="worldtwin-cli",
        evidence_ids=("cli-demo-telemetry-auth",),
        required_evidence=(worldtwin.RequiredEvidence("telemetry authentication receipt"),),
    )
    ledger = worldtwin.create_assumption_ledger(
        assumptions=(assumption,),
        created_at=DEMO_CREATED_AT,
        owner="worldtwin-cli",
        scenario_id=scenario.scenario_id,
    )
    constraints = worldtwin.create_constraint_set(
        rules=(
            worldtwin.create_constraint_rule(
                name="Temperature review limit",
                target="temperature",
                operator=worldtwin.ConstraintOperator.LESS_THAN_OR_EQUAL,
                severity=worldtwin.ConstraintSeverity.CRITICAL,
                description="Predicted temperature must stay under the review limit.",
                limit_value=180.0,
                is_hard=True,
            ),
            worldtwin.create_constraint_rule(
                name="Risk caution band",
                target="risk_score",
                operator=worldtwin.ConstraintOperator.LESS_THAN_OR_EQUAL,
                severity=worldtwin.ConstraintSeverity.WARNING,
                description="Risk score above this value should trigger caution.",
                limit_value=0.70,
                is_hard=False,
            ),
        ),
        created_at=DEMO_CREATED_AT,
        owner="worldtwin-cli",
        scenario_id=scenario.scenario_id,
    )

    return worldtwin.evaluate_worldtwin_policy(
        scenario=scenario,
        assumption_ledger=ledger,
        constraint_set=constraints,
        predicted_values=simulation.predicted_values(),
        created_at=DEMO_CREATED_AT,
        evaluator="worldtwin-cli",
    )


def _observed_state(prediction: worldtwin.PredictionResult) -> worldtwin.WorldState:
    return worldtwin.create_observed_state(
        dimensions=(
            worldtwin.StateDimension(
                name="temperature",
                value=87.5,
                unit="F",
                description="CLI demo observed final temperature.",
            ),
            worldtwin.StateDimension(
                name="risk_score",
                value=0.55,
                unit="score",
                description="CLI demo observed final risk score.",
            ),
        ),
        valid_at=prediction.final_state.valid_at + timedelta(minutes=1),
        created_at=DEMO_CREATED_AT,
        source="cli-demo-observation",
        lineage=(prediction.final_state.state_id,),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ix-blackfox-worldtwin",
        description="Build deterministic IX-BlackFox-WorldTwin review evidence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser(
        "run-demo",
        help="Emit a deterministic Wave 1 review bundle as canonical JSON.",
    )
    demo_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the review bundle JSON.",
    )

    return parser


def _unreachable_command(command: str | None) -> NoReturn:
    raise RuntimeError(f"unsupported command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())

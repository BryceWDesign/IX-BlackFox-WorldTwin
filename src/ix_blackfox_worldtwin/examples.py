"""CI-safe Wave 1 example scenarios for IX-BlackFox-WorldTwin.

These examples are intentionally dependency-light and deterministic. They give
reviewers concrete scenario manifests without requiring GPUs, external physics
engines, network access, or live telemetry.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ix_blackfox_worldtwin.scenario import (
    MeasurableOutput,
    ScenarioBoundary,
    ScenarioBoundaryKind,
    ScenarioManifest,
    ScenarioVariable,
    ScenarioVariableKind,
    create_scenario_manifest,
)
from ix_blackfox_worldtwin.state import StateDimension, create_observed_state

EXAMPLE_CREATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EXAMPLE_CREATOR = "ix-blackfox-worldtwin-example-suite"


def build_thermal_drift_scenario() -> ScenarioManifest:
    """Build a bounded thermal-drift scenario for a bench controller.

    The scenario asks whether a system remains inside review limits after a
    bounded load command. It is not a physics claim. It is a replayable example
    manifest that later simulation and prediction layers can consume.
    """

    initial_state = create_observed_state(
        dimensions=(
            StateDimension(
                name="temperature",
                value=72.0,
                unit="F",
                description="Observed controller temperature.",
                tags=("thermal", "sensor"),
            ),
            StateDimension(
                name="load",
                value=0.40,
                unit="ratio",
                description="Observed normalized load.",
                tags=("control", "input"),
            ),
        ),
        valid_at=EXAMPLE_CREATED_AT,
        created_at=EXAMPLE_CREATED_AT,
        source="example-thermal-telemetry",
        notes=("deterministic CI example",),
    )

    return create_scenario_manifest(
        title="Thermal drift under bounded load",
        system_under_test="bench-controller-alpha",
        purpose=(
            "Estimate whether the controller remains inside thermal review "
            "limits during a bounded load change."
        ),
        initial_state=initial_state,
        boundaries=(
            ScenarioBoundary(
                name="fifteen-minute-window",
                kind=ScenarioBoundaryKind.TEMPORAL,
                description="Scenario may only project fifteen minutes ahead.",
            ),
            ScenarioBoundary(
                name="human-review-required",
                kind=ScenarioBoundaryKind.HUMAN_REVIEW,
                description="Scenario output remains review evidence, not action authority.",
            ),
            ScenarioBoundary(
                name="thermal-safety-envelope",
                kind=ScenarioBoundaryKind.SAFETY,
                description="Scenario must flag predicted temperature above review limits.",
            ),
        ),
        variables=(
            ScenarioVariable(
                name="temperature",
                kind=ScenarioVariableKind.OBSERVED,
                unit="F",
                description="Observed controller temperature.",
                minimum=-40.0,
                maximum=220.0,
            ),
            ScenarioVariable(
                name="load",
                kind=ScenarioVariableKind.CONTROLLED,
                unit="ratio",
                description="Normalized load command.",
                minimum=0.0,
                maximum=1.0,
            ),
            ScenarioVariable(
                name="ambient_disturbance",
                kind=ScenarioVariableKind.DISTURBANCE,
                unit="F",
                description="Bounded ambient temperature disturbance.",
                minimum=-20.0,
                maximum=130.0,
            ),
            ScenarioVariable(
                name="risk_score",
                kind=ScenarioVariableKind.DERIVED,
                unit="score",
                description="Derived review risk score.",
                minimum=0.0,
                maximum=1.0,
            ),
        ),
        expected_outputs=(
            MeasurableOutput(
                name="temperature",
                unit="F",
                description="Predicted temperature at the end of the scenario window.",
            ),
            MeasurableOutput(
                name="risk_score",
                unit="score",
                description="Bounded review risk score for the predicted state.",
            ),
        ),
        created_at=EXAMPLE_CREATED_AT,
        created_by=EXAMPLE_CREATOR,
        evidence_ids=("telemetry-evidence-example-thermal",),
        tags=("thermal", "bounded", "ci-safe"),
    )


def build_resource_pressure_scenario() -> ScenarioManifest:
    """Build a bounded resource-pressure scenario for an AI-agent plan review.

    The scenario asks whether resource usage may cross review limits before
    execution. It keeps WorldTwin focused on evidence generation rather than
    execution authority.
    """

    initial_state = create_observed_state(
        dimensions=(
            StateDimension(
                name="cpu_load",
                value=0.55,
                unit="ratio",
                description="Observed normalized CPU load.",
                tags=("resource", "telemetry"),
            ),
            StateDimension(
                name="memory_pressure",
                value=0.62,
                unit="ratio",
                description="Observed normalized memory pressure.",
                tags=("resource", "telemetry"),
            ),
            StateDimension(
                name="task_parallelism",
                value=2.0,
                unit="count",
                description="Observed parallel task count.",
                tags=("agent", "execution-plan"),
            ),
        ),
        valid_at=EXAMPLE_CREATED_AT,
        created_at=EXAMPLE_CREATED_AT,
        source="example-resource-telemetry",
        notes=("deterministic CI example",),
    )

    return create_scenario_manifest(
        title="Resource pressure before agent-plan execution",
        system_under_test="agent-workflow-runner-alpha",
        purpose=(
            "Estimate whether a proposed AI-agent plan may exceed bounded "
            "resource-review limits before execution is considered."
        ),
        initial_state=initial_state,
        boundaries=(
            ScenarioBoundary(
                name="ten-minute-window",
                kind=ScenarioBoundaryKind.TEMPORAL,
                description="Scenario may only project ten minutes ahead.",
            ),
            ScenarioBoundary(
                name="human-review-required",
                kind=ScenarioBoundaryKind.HUMAN_REVIEW,
                description="Scenario output must be reviewed before execution gating.",
            ),
            ScenarioBoundary(
                name="resource-policy-envelope",
                kind=ScenarioBoundaryKind.POLICY,
                description="Scenario must flag projected resource pressure above policy limits.",
            ),
        ),
        variables=(
            ScenarioVariable(
                name="cpu_load",
                kind=ScenarioVariableKind.OBSERVED,
                unit="ratio",
                description="Observed normalized CPU load.",
                minimum=0.0,
                maximum=1.0,
            ),
            ScenarioVariable(
                name="memory_pressure",
                kind=ScenarioVariableKind.OBSERVED,
                unit="ratio",
                description="Observed normalized memory pressure.",
                minimum=0.0,
                maximum=1.0,
            ),
            ScenarioVariable(
                name="task_parallelism",
                kind=ScenarioVariableKind.CONTROLLED,
                unit="count",
                description="Proposed parallel task count.",
                minimum=1.0,
                maximum=8.0,
            ),
            ScenarioVariable(
                name="risk_score",
                kind=ScenarioVariableKind.DERIVED,
                unit="score",
                description="Derived review risk score.",
                minimum=0.0,
                maximum=1.0,
            ),
        ),
        expected_outputs=(
            MeasurableOutput(
                name="cpu_load",
                unit="ratio",
                description="Predicted CPU load at the end of the scenario window.",
            ),
            MeasurableOutput(
                name="memory_pressure",
                unit="ratio",
                description="Predicted memory pressure at the end of the scenario window.",
            ),
            MeasurableOutput(
                name="risk_score",
                unit="score",
                description="Bounded review risk score for the predicted state.",
            ),
        ),
        created_at=EXAMPLE_CREATED_AT,
        created_by=EXAMPLE_CREATOR,
        evidence_ids=("telemetry-evidence-example-resource",),
        tags=("resource-pressure", "bounded", "ci-safe"),
    )


def get_wave1_example_scenarios() -> tuple[ScenarioManifest, ...]:
    """Return all deterministic Wave 1 example scenarios."""

    return (
        build_thermal_drift_scenario(),
        build_resource_pressure_scenario(),
    )

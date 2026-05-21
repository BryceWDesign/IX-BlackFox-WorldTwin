"""Canonical doctrine and claim boundaries for IX-BlackFox-WorldTwin.

This module keeps project positioning rules in executable form. The rules are
not marketing copy; they are guardrails that keep the repository honest about
what it does, what it does not do, and how it fits beside the broader BlackFox
family without claiming production safety, certification, affiliation, or AGI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemRole:
    """A bounded responsibility inside the BlackFox triad."""

    component: str
    responsibility: str
    boundary: str


@dataclass(frozen=True, slots=True)
class ClaimBoundaryRule:
    """A prohibited or restricted claim with a safer replacement."""

    rule_id: str
    phrase: str
    reason: str
    safer_language: str


@dataclass(frozen=True, slots=True)
class ClaimBoundaryViolation:
    """A detected violation of a claim-boundary rule."""

    rule_id: str
    matched_phrase: str
    reason: str
    safer_language: str


TRIAD_ROLES = (
    SystemRole(
        component="IX-BlackFox-Cognition",
        responsibility="structures intent, claims, uncertainty, plans, and review obligations",
        boundary="does not execute actions or grant authority",
    ),
    SystemRole(
        component="IX-BlackFox-WorldTwin",
        responsibility=(
            "tests bounded scenarios, tracks assumptions, scores prediction error, "
            "and produces simulation evidence"
        ),
        boundary="does not authorize action, execute action, or claim real-world certainty",
    ),
    SystemRole(
        component="IX-BlackFox",
        responsibility="governs execution through policy gates, receipts, and reviewable evidence",
        boundary="does not turn model output into authority without human authorization",
    ),
)

CANONICAL_DOCTRINE = (
    "Cognition structures intent; WorldTwin tests possible consequences; "
    "BlackFox governs execution; humans authorize; evidence decides trust."
)

WORLD_TWIN_FOUNDATIONAL_RULES = (
    "Predictions are evidence, not authority.",
    "Simulated outcomes must remain accountable to observed outcomes.",
    "Assumptions must be explicit before a prediction can be trusted.",
    "Prediction errors must reduce confidence instead of being ignored.",
    "Learning or adaptation must be proposed, tested, reviewed, and reversible.",
    "WorldTwin may recommend caution, denial, quarantine, or review; it may not execute action.",
)

CLAIM_BOUNDARY_RULES = (
    ClaimBoundaryRule(
        rule_id="no-agi-claim",
        phrase="AGI",
        reason=(
            "The project is a governed simulation evidence kernel, not artificial "
            "general intelligence."
        ),
        safer_language="governed world-model evidence layer",
    ),
    ClaimBoundaryRule(
        rule_id="no-autonomous-authority",
        phrase="autonomous authority",
        reason=(
            "The project produces reviewable evidence and must not imply authority "
            "to act alone."
        ),
        safer_language="human-reviewable execution evidence",
    ),
    ClaimBoundaryRule(
        rule_id="no-production-readiness",
        phrase="production-ready",
        reason=(
            "The project is a research prototype and has not been validated for "
            "production deployment."
        ),
        safer_language="research prototype",
    ),
    ClaimBoundaryRule(
        rule_id="no-certification",
        phrase="certified",
        reason=(
            "The project has not been certified by a safety, security, compliance, "
            "or government body."
        ),
        safer_language="tested prototype evidence",
    ),
    ClaimBoundaryRule(
        rule_id="no-defense-affiliation",
        phrase="defense-approved",
        reason="The project must not imply official defense approval or affiliation.",
        safer_language="independent source-available research prototype",
    ),
    ClaimBoundaryRule(
        rule_id="no-government-affiliation",
        phrase="government-approved",
        reason="The project must not imply official government approval or affiliation.",
        safer_language="independent source-available research prototype",
    ),
    ClaimBoundaryRule(
        rule_id="no-real-world-authority",
        phrase="real-world predictive authority",
        reason="Predictions must remain bounded evidence, not a claim of authority over reality.",
        safer_language="bounded prediction evidence",
    ),
)


def get_triad_roles() -> tuple[SystemRole, ...]:
    """Return the bounded roles of the three-part BlackFox architecture."""

    return TRIAD_ROLES


def get_worldtwin_foundational_rules() -> tuple[str, ...]:
    """Return the foundational operating rules for WorldTwin."""

    return WORLD_TWIN_FOUNDATIONAL_RULES


def get_claim_boundary_rules() -> tuple[ClaimBoundaryRule, ...]:
    """Return claim-boundary rules used to keep public language honest."""

    return CLAIM_BOUNDARY_RULES


def find_claim_boundary_violations(text: str) -> tuple[ClaimBoundaryViolation, ...]:
    """Find claim-boundary violations in arbitrary project language."""

    folded_text = text.casefold()
    violations: list[ClaimBoundaryViolation] = []

    for rule in CLAIM_BOUNDARY_RULES:
        if rule.phrase.casefold() in folded_text:
            violations.append(
                ClaimBoundaryViolation(
                    rule_id=rule.rule_id,
                    matched_phrase=rule.phrase,
                    reason=rule.reason,
                    safer_language=rule.safer_language,
                )
            )

    return tuple(violations)


def is_claim_language_allowed(text: str) -> bool:
    """Return True when text does not violate canonical claim boundaries."""

    return find_claim_boundary_violations(text) == ()


def render_doctrine_summary() -> str:
    """Return the concise canonical doctrine summary."""

    return CANONICAL_DOCTRINE

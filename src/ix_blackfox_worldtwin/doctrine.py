"""Doctrine and claim-boundary contracts for IX-BlackFox-WorldTwin.

This module keeps the project language bounded. IX-BlackFox-WorldTwin is a
world-model and simulation evidence layer; it is not an AGI, not an autonomous
authority, not a certified runtime, and not a defense-approved system.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SystemRole(StrEnum):
    """Canonical roles in the IX-BlackFox ecosystem."""

    COGNITION = "cognition"
    WORLD_TWIN = "world-twin"
    EXECUTION_GOVERNANCE = "execution-governance"


@dataclass(frozen=True, slots=True)
class TriadRole:
    """A named role, responsibility, and boundary in the IX-BlackFox triad."""

    component: str
    responsibility: str
    boundary: str


@dataclass(frozen=True, slots=True)
class ClaimBoundaryRule:
    """A prohibited claim and its safer replacement direction."""

    rule_id: str
    phrase: str
    reason: str
    safer_language: str


@dataclass(frozen=True, slots=True)
class ClaimBoundaryViolation:
    """A detected claim-boundary violation."""

    rule_id: str
    matched_phrase: str
    reason: str
    safer_language: str


CANONICAL_DOCTRINE = (
    "Model thinks -> Cognition structures -> WorldTwin tests possible consequences -> "
    "BlackFox governs execution -> humans authorize -> evidence decides trust."
)

TRIAD_ROLES: tuple[TriadRole, ...] = (
    TriadRole(
        component="IX-BlackFox-Cognition",
        responsibility=(
            "structures intent, claims, plans, beliefs, and model-side reasoning into "
            "inspectable cognitive artifacts"
        ),
        boundary=("does not execute actions, certify claims, or bypass downstream evidence gates"),
    ),
    TriadRole(
        component="IX-BlackFox-WorldTwin",
        responsibility=(
            "tests bounded scenarios, assumptions, constraints, predicted consequences, "
            "and reality-delta evidence before execution handoff"
        ),
        boundary=(
            "does not authorize action, certify safety, or turn predicted outcomes into authority"
        ),
    ),
    TriadRole(
        component="IX-BlackFox",
        responsibility=(
            "governs proposed execution through policy gates, receipts, evidence bundles, "
            "workspace controls, and reviewable handoff packages"
        ),
        boundary=(
            "does not execute proposed changes without human authorization and explicit review"
        ),
    ),
)

WORLD_TWIN_FOUNDATIONAL_RULES: tuple[str, ...] = (
    "Predictions are evidence, not authority.",
    "Simulated outcomes must remain accountable to observed outcomes.",
    "WorldTwin may not execute action or authorize execution.",
    "WorldTwin does not certify safety, legality, military suitability, or production readiness.",
    "WorldTwin predictions are bounded by stated assumptions, scenario scope, and evidence inputs.",
    "WorldTwin outputs must be reviewable before any BlackFox execution-governance handoff.",
    "WorldTwin evidence must preserve provenance, replayability, confidence, and uncertainty.",
    "WorldTwin must fail closed when assumptions, constraints, evidence, or review authority "
    "are missing.",
)

CLAIM_BOUNDARY_RULES: tuple[ClaimBoundaryRule, ...] = (
    ClaimBoundaryRule(
        rule_id="no-agi-claim",
        phrase="AGI",
        reason=(
            "The project is governed simulation infrastructure, not an artificial general "
            "intelligence."
        ),
        safer_language="governed world-model evidence layer",
    ),
    ClaimBoundaryRule(
        rule_id="no-autonomous-authority",
        phrase="autonomous authority",
        reason=(
            "The project produces reviewable evidence and must not imply authority to act " "alone."
        ),
        safer_language="human-reviewable execution evidence",
    ),
    ClaimBoundaryRule(
        rule_id="no-certification",
        phrase="certified",
        reason="No certification, accreditation, or regulatory approval is claimed.",
        safer_language="bounded evidence for review",
    ),
    ClaimBoundaryRule(
        rule_id="no-defense-affiliation",
        phrase="defense-approved",
        reason=(
            "The project is not endorsed, approved, funded, or certified by defense " "authorities."
        ),
        safer_language="defense-relevant research prototype",
    ),
    ClaimBoundaryRule(
        rule_id="no-production-readiness",
        phrase="production-ready",
        reason="The current state is a research prototype and must not be described as deployable.",
        safer_language="research prototype or evaluation prototype",
    ),
)


def get_triad_roles() -> tuple[TriadRole, ...]:
    """Return the canonical IX-BlackFox ecosystem role split."""

    return TRIAD_ROLES


def get_worldtwin_foundational_rules() -> tuple[str, ...]:
    """Return the foundational WorldTwin rules."""

    return WORLD_TWIN_FOUNDATIONAL_RULES


def get_claim_boundary_rules() -> tuple[ClaimBoundaryRule, ...]:
    """Return prohibited claim-boundary rules."""

    return CLAIM_BOUNDARY_RULES


def find_claim_boundary_violations(text: str) -> tuple[ClaimBoundaryViolation, ...]:
    """Return claim-boundary violations found in supplied text."""

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
    """Return True when text does not violate project claim boundaries."""

    return not find_claim_boundary_violations(text)


def render_doctrine_summary() -> str:
    """Render the compact canonical doctrine summary."""

    return CANONICAL_DOCTRINE

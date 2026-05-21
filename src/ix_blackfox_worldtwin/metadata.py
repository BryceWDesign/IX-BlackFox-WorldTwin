"""Stable project identity metadata for IX-BlackFox-WorldTwin.

This module intentionally contains only dependency-light package identity values.
It does not import future simulation, scenario, assumption, receipt, delta,
adaptation, or handoff modules, so the public API can remain stable while the
Wave 1 governed simulation evidence kernel evolves.
"""

from __future__ import annotations

from dataclasses import dataclass

PROJECT_NAME = "IX-BlackFox-WorldTwin"
PACKAGE_NAME = "ix_blackfox_worldtwin"
VERSION = "0.1.0"
LICENSE_NAME = "IX-BlackFox-WorldTwin Source-Available Evaluation License v1.0"
REPOSITORY_URL = "https://github.com/BryceWDesign/IX-BlackFox-WorldTwin"
COMMERCIAL_LICENSING_URL = "https://www.linkedin.com/in/brycewdesign/"

GITHUB_DESCRIPTION_LIMIT = 299
GITHUB_DESCRIPTION = (
    "A governed world-model evidence layer for AI agents: simulate bounded scenarios, "
    "track assumptions, score prediction-vs-reality error, and produce human-reviewable "
    "execution evidence."
)

GITHUB_TOPICS = (
    "ai-agents",
    "simulation",
    "digital-twin",
    "world-model",
    "agent-governance",
    "runtime-assurance",
    "evidence",
    "prediction",
    "scenario-testing",
    "assumption-ledger",
    "reality-delta",
    "human-review",
    "policy-gates",
    "receipts",
    "model-evaluation",
    "risk-analysis",
    "test-evaluation",
    "safe-ai",
    "ai-safety",
    "decision-support",
)

DESCRIPTION_FORBIDDEN_TERMS = (
    "IX-BlackFox-Cognition",
    "BlackFox/Cognition",
    "Cognition handoff",
    "AGI",
    "autonomous AGI",
    "self-aware",
    "defense-approved",
    "government-approved",
    "production-ready",
    "certified",
)

CORE_DOCTRINE = (
    "Cognition structures intent → WorldTwin tests possible consequences → "
    "BlackFox governs execution → humans authorize → evidence decides trust."
)

FOUNDATIONAL_LAW = (
    "Do not treat predicted futures as authority. Treat predictions as bounded, "
    "reviewable evidence that must remain accountable to observed reality."
)

PUBLIC_DESCRIPTION = (
    "IX-BlackFox-WorldTwin is a source-available governed world-model evidence "
    "layer for AI agents: it simulates bounded scenarios, tracks assumptions, "
    "scores prediction-vs-reality error, produces receipts, and packages "
    "human-reviewable execution evidence before action."
)

RESEARCH_STATUS = "research-prototype"

PROHIBITED_CLAIMS = (
    "AGI",
    "autonomous AGI",
    "self-aware",
    "production-ready",
    "certified",
    "government-affiliated",
    "defense-affiliated",
    "autonomous authority",
    "real-world predictive authority",
)


@dataclass(frozen=True, slots=True)
class PackageIdentity:
    """Stable public identity information for the package."""

    project_name: str
    package_name: str
    version: str
    license_name: str
    research_status: str
    doctrine: str
    foundational_law: str
    public_description: str
    github_description: str
    github_description_limit: int
    github_topics: tuple[str, ...]
    repository_url: str
    commercial_licensing_url: str
    prohibited_claims: tuple[str, ...]


def get_package_identity() -> PackageIdentity:
    """Return immutable package identity metadata."""

    return PackageIdentity(
        project_name=PROJECT_NAME,
        package_name=PACKAGE_NAME,
        version=VERSION,
        license_name=LICENSE_NAME,
        research_status=RESEARCH_STATUS,
        doctrine=CORE_DOCTRINE,
        foundational_law=FOUNDATIONAL_LAW,
        public_description=PUBLIC_DESCRIPTION,
        github_description=GITHUB_DESCRIPTION,
        github_description_limit=GITHUB_DESCRIPTION_LIMIT,
        github_topics=GITHUB_TOPICS,
        repository_url=REPOSITORY_URL,
        commercial_licensing_url=COMMERCIAL_LICENSING_URL,
        prohibited_claims=PROHIBITED_CLAIMS,
    )


def get_github_description() -> str:
    """Return the approved GitHub repository description."""

    return GITHUB_DESCRIPTION


def get_github_topics() -> tuple[str, ...]:
    """Return the approved GitHub repository topics."""

    return GITHUB_TOPICS


def get_external_description_issues(description: str) -> tuple[str, ...]:
    """Return blocking issues for an external-facing repository description."""

    issues: list[str] = []

    if len(description) > GITHUB_DESCRIPTION_LIMIT:
        issues.append("description exceeds GitHub description limit")

    folded_description = description.casefold()
    for forbidden_term in DESCRIPTION_FORBIDDEN_TERMS:
        if forbidden_term.casefold() in folded_description:
            issues.append(f"description contains prohibited or insider term: {forbidden_term}")

    return tuple(issues)


def is_prohibited_claim(claim: str) -> bool:
    """Return True when a claim violates the project identity boundary."""

    folded_claim = claim.casefold()
    return any(prohibited.casefold() == folded_claim for prohibited in PROHIBITED_CLAIMS)

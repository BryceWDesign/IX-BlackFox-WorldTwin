"""Project metadata for IX-BlackFox-WorldTwin.

The values in this module are intentionally conservative because repository
metadata is often the first thing reviewers, scanners, and downstream users see.
"""

from __future__ import annotations

from dataclasses import dataclass

PROJECT_NAME = "IX-BlackFox-WorldTwin"
PACKAGE_NAME = "ix_blackfox_worldtwin"
VERSION = "0.1.0"

LICENSE_NAME = "Source-Available Evaluation License"
RESEARCH_STATUS = "research-prototype"

REPOSITORY_URL = "https://github.com/BryceWDesign/IX-BlackFox-WorldTwin"
COMMERCIAL_LICENSING_URL = "https://www.linkedin.com/in/brycewdesign/"

FOUNDATIONAL_LAW = (
    "WorldTwin creates bounded, reviewable evidence for consequence testing; it does not "
    "authorize execution."
)

CORE_DOCTRINE = (
    "Model thinks -> Cognition structures -> WorldTwin tests possible consequences -> "
    "BlackFox governs execution -> humans authorize -> evidence decides trust."
)

PUBLIC_DESCRIPTION = (
    "Source-available governed world-model evidence layer for AI-agent decisions and "
    "human-reviewable execution evidence."
)

GITHUB_DESCRIPTION = PUBLIC_DESCRIPTION
GITHUB_DESCRIPTION_LIMIT = 299

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
    "AGI",
    "autonomous AGI",
    "self-aware",
    "production-ready",
    "defense-approved",
    "government-approved",
    "production approved",
    "certified",
)

PROHIBITED_CLAIMS = (
    "AGI",
    "autonomous AGI",
    "self-aware",
    "production-ready",
    "production approved",
    "certified",
    "government-affiliated",
    "defense-affiliated",
    "defense-approved",
    "government-approved",
    "operationally deployed",
    "real-world predictive authority",
)


@dataclass(frozen=True, slots=True)
class PackageIdentity:
    """Stable identity metadata for package and repository checks."""

    project_name: str
    package_name: str
    version: str
    license_name: str
    research_status: str
    repository_url: str
    commercial_licensing_url: str
    foundational_law: str
    doctrine: str
    core_doctrine: str
    public_description: str
    github_description: str
    github_description_limit: int
    github_topics: tuple[str, ...]
    prohibited_claims: tuple[str, ...]


def get_package_identity() -> PackageIdentity:
    """Return stable package identity metadata."""

    return PackageIdentity(
        project_name=PROJECT_NAME,
        package_name=PACKAGE_NAME,
        version=VERSION,
        license_name=LICENSE_NAME,
        research_status=RESEARCH_STATUS,
        repository_url=REPOSITORY_URL,
        commercial_licensing_url=COMMERCIAL_LICENSING_URL,
        foundational_law=FOUNDATIONAL_LAW,
        doctrine=CORE_DOCTRINE,
        core_doctrine=CORE_DOCTRINE,
        public_description=PUBLIC_DESCRIPTION,
        github_description=GITHUB_DESCRIPTION,
        github_description_limit=GITHUB_DESCRIPTION_LIMIT,
        github_topics=GITHUB_TOPICS,
        prohibited_claims=PROHIBITED_CLAIMS,
    )


def get_github_description() -> str:
    """Return the GitHub About description."""

    return GITHUB_DESCRIPTION


def get_github_topics() -> tuple[str, ...]:
    """Return GitHub repository topics."""

    return GITHUB_TOPICS


def get_external_description_issues(description: str) -> tuple[str, ...]:
    """Return conservative issues for public repository descriptions."""

    normalized_description = description.strip()
    if not normalized_description:
        return ("description is empty",)
    if len(normalized_description) > GITHUB_DESCRIPTION_LIMIT:
        return ("description exceeds GitHub description limit",)

    folded_description = normalized_description.casefold()
    issues: list[str] = []

    for forbidden in DESCRIPTION_FORBIDDEN_TERMS:
        if forbidden.casefold() in folded_description:
            issues.append(f"description contains prohibited or insider term: {forbidden}")

    return tuple(issues)


def is_prohibited_claim(claim: str) -> bool:
    """Return True when a claim violates the project identity boundary."""

    folded_claim = claim.casefold()
    return any(prohibited.casefold() in folded_claim for prohibited in PROHIBITED_CLAIMS)

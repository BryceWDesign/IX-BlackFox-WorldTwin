"""Project metadata for IX-BlackFox-WorldTwin.

The values in this module are intentionally conservative because repository
metadata is often the first thing reviewers, scanners, and downstream users see.
"""

from __future__ import annotations

from dataclasses import dataclass

PROJECT_NAME = "IX-BlackFox-WorldTwin"
PACKAGE_NAME = "ix-blackfox-worldtwin"
VERSION = "0.1.0"

LICENSE_NAME = "Source-Available Evaluation License"
RESEARCH_STATUS = "source-available research prototype"

REPOSITORY_URL = "https://github.com/BryceWDesign/IX-BlackFox-WorldTwin"

FOUNDATIONAL_LAW = (
    "WorldTwin simulates and records consequence evidence; it does not authorize execution."
)

CORE_DOCTRINE = (
    "Model thinks -> Cognition structures -> WorldTwin tests consequences -> "
    "BlackFox governs execution -> humans authorize -> evidence decides trust."
)

PUBLIC_DESCRIPTION = (
    "Source-available governed world-model and simulation evidence layer for "
    "AI-agent decisions; not AGI, not autonomous authority, and not production-ready."
)

GITHUB_DESCRIPTION = (
    "Source-available governed world-model evidence layer for AI-agent decisions."
)
GITHUB_DESCRIPTION_LIMIT = 350

GITHUB_TOPICS = (
    "ai-governance",
    "world-model",
    "simulation",
    "runtime-assurance",
    "evidence",
    "human-review",
    "source-available",
)

DESCRIPTION_FORBIDDEN_TERMS = (
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
    foundational_law: str
    core_doctrine: str
    public_description: str


def get_package_identity() -> PackageIdentity:
    """Return stable package identity metadata."""

    return PackageIdentity(
        project_name=PROJECT_NAME,
        package_name=PACKAGE_NAME,
        version=VERSION,
        license_name=LICENSE_NAME,
        research_status=RESEARCH_STATUS,
        repository_url=REPOSITORY_URL,
        foundational_law=FOUNDATIONAL_LAW,
        core_doctrine=CORE_DOCTRINE,
        public_description=PUBLIC_DESCRIPTION,
    )


def get_github_description() -> str:
    """Return the GitHub About description."""

    return GITHUB_DESCRIPTION


def get_github_topics() -> tuple[str, ...]:
    """Return GitHub repository topics."""

    return GITHUB_TOPICS


def get_external_description_issues(description: str) -> tuple[str, ...]:
    """Return conservative issues for public repository descriptions."""

    issues: list[str] = []

    if not description.strip():
        issues.append("description is empty")
    if len(description) > GITHUB_DESCRIPTION_LIMIT:
        issues.append("description exceeds GitHub description length limit")

    folded_description = description.casefold()
    for forbidden in DESCRIPTION_FORBIDDEN_TERMS:
        if forbidden.casefold() in folded_description:
            issues.append(f"description uses prohibited claim language: {forbidden}")

    if "world-model" not in folded_description and "simulation" not in folded_description:
        issues.append("description should identify the repository as world-model or simulation work")
    if "evidence" not in folded_description:
        issues.append("description should mention evidence")
    if "source-available" not in folded_description:
        issues.append("description should identify the source-available posture")

    return tuple(issues)


def is_prohibited_claim(claim: str) -> bool:
    """Return True when a claim violates the project identity boundary."""

    folded_claim = claim.casefold()
    return any(prohibited.casefold() in folded_claim for prohibited in PROHIBITED_CLAIMS)

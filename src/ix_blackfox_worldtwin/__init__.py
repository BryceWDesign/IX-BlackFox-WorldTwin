"""IX-BlackFox-WorldTwin public API.

IX-BlackFox-WorldTwin is a source-available governed world-model evidence layer
for AI-agent decisions.

The current public API exports stable project metadata and doctrine boundaries.
Later Wave 1 commits will add scenario manifests, assumption ledgers, constraint
checks, deterministic simulation, branching predictions, receipts,
reality-delta scoring, model-confidence tracking, adaptation gates, and
human-reviewable handoff packages without weakening this package boundary.
"""

from ix_blackfox_worldtwin.doctrine import (
    CANONICAL_DOCTRINE,
    CLAIM_BOUNDARY_RULES,
    TRIAD_ROLES,
    WORLD_TWIN_FOUNDATIONAL_RULES,
    ClaimBoundaryRule,
    ClaimBoundaryViolation,
    SystemRole,
    find_claim_boundary_violations,
    get_claim_boundary_rules,
    get_triad_roles,
    get_worldtwin_foundational_rules,
    is_claim_language_allowed,
    render_doctrine_summary,
)
from ix_blackfox_worldtwin.metadata import (
    CORE_DOCTRINE,
    DESCRIPTION_FORBIDDEN_TERMS,
    FOUNDATIONAL_LAW,
    GITHUB_DESCRIPTION,
    GITHUB_DESCRIPTION_LIMIT,
    GITHUB_TOPICS,
    LICENSE_NAME,
    PACKAGE_NAME,
    PROHIBITED_CLAIMS,
    PROJECT_NAME,
    PUBLIC_DESCRIPTION,
    REPOSITORY_URL,
    RESEARCH_STATUS,
    VERSION,
    PackageIdentity,
    get_external_description_issues,
    get_github_description,
    get_github_topics,
    get_package_identity,
    is_prohibited_claim,
)

__all__ = [
    "CANONICAL_DOCTRINE",
    "CLAIM_BOUNDARY_RULES",
    "CORE_DOCTRINE",
    "DESCRIPTION_FORBIDDEN_TERMS",
    "FOUNDATIONAL_LAW",
    "GITHUB_DESCRIPTION",
    "GITHUB_DESCRIPTION_LIMIT",
    "GITHUB_TOPICS",
    "LICENSE_NAME",
    "PACKAGE_NAME",
    "PROHIBITED_CLAIMS",
    "PROJECT_NAME",
    "PUBLIC_DESCRIPTION",
    "REPOSITORY_URL",
    "RESEARCH_STATUS",
    "TRIAD_ROLES",
    "VERSION",
    "WORLD_TWIN_FOUNDATIONAL_RULES",
    "ClaimBoundaryRule",
    "ClaimBoundaryViolation",
    "PackageIdentity",
    "SystemRole",
    "find_claim_boundary_violations",
    "get_claim_boundary_rules",
    "get_external_description_issues",
    "get_github_description",
    "get_github_topics",
    "get_package_identity",
    "get_triad_roles",
    "get_worldtwin_foundational_rules",
    "is_claim_language_allowed",
    "is_prohibited_claim",
    "render_doctrine_summary",
]

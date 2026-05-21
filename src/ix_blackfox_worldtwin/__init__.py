"""IX-BlackFox-WorldTwin public API.

IX-BlackFox-WorldTwin is a source-available governed world-model evidence layer
for AI-agent decisions.

The current public API exports stable project metadata only. Later Wave 1
commits will add scenario manifests, assumption ledgers, constraint checks,
deterministic simulation, branching predictions, receipts, reality-delta
scoring, model-confidence tracking, adaptation gates, and human-reviewable
handoff packages without weakening this package boundary.
"""

from ix_blackfox_worldtwin.metadata import (
    CORE_DOCTRINE,
    FOUNDATIONAL_LAW,
    LICENSE_NAME,
    PACKAGE_NAME,
    PROHIBITED_CLAIMS,
    PROJECT_NAME,
    PUBLIC_DESCRIPTION,
    RESEARCH_STATUS,
    VERSION,
    PackageIdentity,
    get_package_identity,
)

__all__ = [
    "CORE_DOCTRINE",
    "FOUNDATIONAL_LAW",
    "LICENSE_NAME",
    "PACKAGE_NAME",
    "PROHIBITED_CLAIMS",
    "PROJECT_NAME",
    "PUBLIC_DESCRIPTION",
    "RESEARCH_STATUS",
    "VERSION",
    "PackageIdentity",
    "get_package_identity",
]

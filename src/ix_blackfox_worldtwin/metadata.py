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
        prohibited_claims=PROHIBITED_CLAIMS,
    )

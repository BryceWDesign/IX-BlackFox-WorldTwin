"""Reproducibility manifests for IX-BlackFox-WorldTwin.

WorldTwin evidence is only useful when it can be replayed, checked, and linked
back to the scenario, simulation, branch, and risk artifacts that produced it.
This module records deterministic fingerprints and verifies that later artifacts
still match the evidence chain they claim to represent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ix_blackfox_worldtwin.branching import BranchComparison
from ix_blackfox_worldtwin.risk import RiskComparison
from ix_blackfox_worldtwin.scenario import ScenarioManifest
from ix_blackfox_worldtwin.simulation import SimulationResult

REPRODUCIBILITY_SCHEMA_VERSION = "reproducibility-manifest-v1"
REPRODUCIBILITY_ID_DIGEST_LENGTH = 16


class ReproducibilityStatus(StrEnum):
    """Status for a reproducibility check."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ReproducibilityArtifact:
    """A fingerprinted artifact that must remain stable across replay."""

    artifact_id: str
    artifact_type: str
    fingerprint: str
    source: str

    def __post_init__(self) -> None:
        """Validate and normalize a reproducibility artifact."""

        object.__setattr__(self, "artifact_id", _require_non_empty(self.artifact_id, "artifact id"))
        object.__setattr__(
            self,
            "artifact_type",
            _require_non_empty(self.artifact_type, "artifact type"),
        )
        object.__setattr__(
            self,
            "fingerprint",
            _require_non_empty(self.fingerprint, "artifact fingerprint"),
        )
        object.__setattr__(self, "source", _require_non_empty(self.source, "artifact source"))

    def canonical_payload(self) -> dict[str, str]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "fingerprint": self.fingerprint,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ReproducibilityManifest:
    """A deterministic manifest for replaying a WorldTwin evidence chain."""

    manifest_id: str
    scenario_id: str
    created_at: datetime
    created_by: str
    artifacts: tuple[ReproducibilityArtifact, ...]
    replay_command: str
    notes: tuple[str, ...] = ()
    schema_version: str = REPRODUCIBILITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a reproducibility manifest."""

        if not self.artifacts:
            raise ValueError("reproducibility manifest requires at least one artifact")

        object.__setattr__(
            self,
            "manifest_id",
            _require_non_empty(self.manifest_id, "manifest id"),
        )
        object.__setattr__(self, "scenario_id", _require_non_empty(self.scenario_id, "scenario id"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_utc_datetime(self.created_at, "manifest created_at"),
        )
        object.__setattr__(self, "created_by", _require_non_empty(self.created_by, "created by"))
        object.__setattr__(self, "artifacts", _normalize_artifacts(self.artifacts))
        object.__setattr__(
            self,
            "replay_command",
            _require_non_empty(self.replay_command, "replay command"),
        )
        object.__setattr__(self, "notes", _normalize_unique_text_tuple(self.notes, "manifest note"))
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "reproducibility schema version"),
        )

    def artifact_table(self) -> dict[str, str]:
        """Return artifact ids mapped to their fingerprints."""

        return {artifact.artifact_id: artifact.fingerprint for artifact in self.artifacts}

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "artifacts": [artifact.canonical_payload() for artifact in self.artifacts],
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "manifest_id": self.manifest_id,
            "notes": list(self.notes),
            "replay_command": self.replay_command,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this manifest."""

        return _stable_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ReproducibilityCheck:
    """Result of checking current artifacts against a manifest."""

    check_id: str
    manifest_id: str
    status: ReproducibilityStatus
    checked_at: datetime
    checked_by: str
    mismatches: tuple[str, ...] = ()
    missing_artifacts: tuple[str, ...] = ()
    schema_version: str = REPRODUCIBILITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate and normalize a reproducibility check."""

        object.__setattr__(self, "check_id", _require_non_empty(self.check_id, "check id"))
        object.__setattr__(self, "manifest_id", _require_non_empty(self.manifest_id, "manifest id"))
        object.__setattr__(
            self,
            "checked_at",
            _require_aware_utc_datetime(self.checked_at, "check checked_at"),
        )
        object.__setattr__(self, "checked_by", _require_non_empty(self.checked_by, "checked by"))
        object.__setattr__(
            self,
            "mismatches",
            _normalize_unique_text_tuple(self.mismatches, "mismatch"),
        )
        object.__setattr__(
            self,
            "missing_artifacts",
            _normalize_unique_text_tuple(self.missing_artifacts, "missing artifact"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _require_non_empty(self.schema_version, "reproducibility schema version"),
        )

        expected_status = (
            ReproducibilityStatus.PASS
            if not self.mismatches and not self.missing_artifacts
            else ReproducibilityStatus.FAIL
        )
        if self.status is not expected_status:
            raise ValueError("reproducibility status must match mismatch and missing-artifact state")

    @property
    def passed(self) -> bool:
        """Return True when the reproducibility check passed."""

        return self.status is ReproducibilityStatus.PASS

    def canonical_payload(self) -> dict[str, Any]:
        """Return a deterministic payload for hashing and receipts."""

        return {
            "check_id": self.check_id,
            "checked_at": self.checked_at.isoformat(),
            "checked_by": self.checked_by,
            "manifest_id": self.manifest_id,
            "mismatches": list(self.mismatches),
            "missing_artifacts": list(self.missing_artifacts),
            "schema_version": self.schema_version,
            "status": self.status.value,
        }

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 fingerprint for this check."""

        return _stable_sha256(self.canonical_payload())


def create_reproducibility_manifest(
    *,
    scenario: ScenarioManifest,
    simulation: SimulationResult,
    created_at: datetime,
    created_by: str,
    branch_comparison: BranchComparison | None = None,
    risk_comparison: RiskComparison | None = None,
    replay_command: str = "python -m ix_blackfox_worldtwin.cli run-demo",
    notes: tuple[str, ...] = (),
    manifest_id: str | None = None,
) -> ReproducibilityManifest:
    """Create a reproducibility manifest from replayable WorldTwin artifacts."""

    if simulation.scenario_id != scenario.scenario_id:
        raise ValueError("simulation scenario_id must match manifest scenario_id")
    if branch_comparison is not None and branch_comparison.scenario_id != scenario.scenario_id:
        raise ValueError("branch comparison scenario_id must match manifest scenario_id")
    if risk_comparison is not None and risk_comparison.scenario_id != scenario.scenario_id:
        raise ValueError("risk comparison scenario_id must match manifest scenario_id")

    artifacts = [
        ReproducibilityArtifact(
            artifact_id=scenario.scenario_id,
            artifact_type="scenario",
            fingerprint=scenario.fingerprint(),
            source="scenario-manifest",
        ),
        ReproducibilityArtifact(
            artifact_id=simulation.simulation_id,
            artifact_type="simulation",
            fingerprint=simulation.fingerprint(),
            source="deterministic-simulation",
        ),
    ]

    if branch_comparison is not None:
        artifacts.append(
            ReproducibilityArtifact(
                artifact_id=branch_comparison.comparison_id,
                artifact_type="branch-comparison",
                fingerprint=branch_comparison.fingerprint(),
                source="branching-simulation",
            )
        )

    if risk_comparison is not None:
        artifacts.append(
            ReproducibilityArtifact(
                artifact_id=risk_comparison.comparison_id,
                artifact_type="risk-comparison",
                fingerprint=risk_comparison.fingerprint(),
                source="risk-scoring",
            )
        )

    normalized_created_at = _require_aware_utc_datetime(created_at, "manifest created_at")
    normalized_created_by = _require_non_empty(created_by, "created by")
    normalized_replay_command = _require_non_empty(replay_command, "replay command")
    normalized_notes = _normalize_unique_text_tuple(notes, "manifest note")
    normalized_artifacts = _normalize_artifacts(tuple(artifacts))
    resolved_manifest_id = manifest_id or make_reproducibility_manifest_id(
        scenario_id=scenario.scenario_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        artifacts=normalized_artifacts,
        replay_command=normalized_replay_command,
        notes=normalized_notes,
    )

    return ReproducibilityManifest(
        manifest_id=resolved_manifest_id,
        scenario_id=scenario.scenario_id,
        created_at=normalized_created_at,
        created_by=normalized_created_by,
        artifacts=normalized_artifacts,
        replay_command=normalized_replay_command,
        notes=normalized_notes,
    )


def check_reproducibility(
    *,
    manifest: ReproducibilityManifest,
    current_artifacts: tuple[ReproducibilityArtifact, ...],
    checked_at: datetime,
    checked_by: str,
    check_id: str | None = None,
) -> ReproducibilityCheck:
    """Compare current artifacts against a reproducibility manifest."""

    expected = manifest.artifact_table()
    current = {
        artifact.artifact_id: artifact.fingerprint
        for artifact in _normalize_artifacts(current_artifacts)
    }

    missing_artifacts = tuple(sorted(artifact_id for artifact_id in expected if artifact_id not in current))
    mismatches = tuple(
        sorted(
            artifact_id
            for artifact_id, expected_fingerprint in expected.items()
            if artifact_id in current and current[artifact_id] != expected_fingerprint
        )
    )
    status = (
        ReproducibilityStatus.PASS
        if not missing_artifacts and not mismatches
        else ReproducibilityStatus.FAIL
    )
    normalized_checked_at = _require_aware_utc_datetime(checked_at, "check checked_at")
    normalized_checked_by = _require_non_empty(checked_by, "checked by")
    resolved_check_id = check_id or make_reproducibility_check_id(
        manifest_id=manifest.manifest_id,
        status=status,
        checked_at=normalized_checked_at,
        checked_by=normalized_checked_by,
        mismatches=mismatches,
        missing_artifacts=missing_artifacts,
    )

    return ReproducibilityCheck(
        check_id=resolved_check_id,
        manifest_id=manifest.manifest_id,
        status=status,
        checked_at=normalized_checked_at,
        checked_by=normalized_checked_by,
        mismatches=mismatches,
        missing_artifacts=missing_artifacts,
    )


def make_reproducibility_manifest_id(
    *,
    scenario_id: str,
    created_at: datetime,
    created_by: str,
    artifacts: tuple[ReproducibilityArtifact, ...],
    replay_command: str,
    notes: tuple[str, ...] = (),
) -> str:
    """Create a deterministic reproducibility manifest id."""

    payload = {
        "artifacts": [
            artifact.canonical_payload() for artifact in _normalize_artifacts(artifacts)
        ],
        "created_at": _require_aware_utc_datetime(
            created_at,
            "manifest created_at",
        ).isoformat(),
        "created_by": _require_non_empty(created_by, "created by"),
        "notes": list(_normalize_unique_text_tuple(notes, "manifest note")),
        "replay_command": _require_non_empty(replay_command, "replay command"),
        "scenario_id": _require_non_empty(scenario_id, "scenario id"),
        "schema_version": REPRODUCIBILITY_SCHEMA_VERSION,
    }
    digest = _stable_sha256(payload)[:REPRODUCIBILITY_ID_DIGEST_LENGTH]
    return f"reproducibility-manifest-{digest}"


def make_reproducibility_check_id(
    *,
    manifest_id: str,
    status: ReproducibilityStatus,
    checked_at: datetime,
    checked_by: str,
    mismatches: tuple[str, ...] = (),
    missing_artifacts: tuple[str, ...] = (),
) -> str:
    """Create a deterministic reproducibility check id."""

    payload = {
        "checked_at": _require_aware_utc_datetime(
            checked_at,
            "check checked_at",
        ).isoformat(),
        "checked_by": _require_non_empty(checked_by, "checked by"),
        "manifest_id": _require_non_empty(manifest_id, "manifest id"),
        "mismatches": list(_normalize_unique_text_tuple(mismatches, "mismatch")),
        "missing_artifacts": list(
            _normalize_unique_text_tuple(missing_artifacts, "missing artifact")
        ),
        "schema_version": REPRODUCIBILITY_SCHEMA_VERSION,
        "status": status.value,
    }
    digest = _stable_sha256(payload)[:REPRODUCIBILITY_ID_DIGEST_LENGTH]
    return f"reproducibility-check-{digest}"


def _normalize_artifacts(
    artifacts: tuple[ReproducibilityArtifact, ...],
) -> tuple[ReproducibilityArtifact, ...]:
    if not artifacts:
        raise ValueError("reproducibility requires at least one artifact")

    seen_artifact_ids: set[str] = set()
    normalized_artifacts: list[ReproducibilityArtifact] = []

    for artifact in artifacts:
        if artifact.artifact_id in seen_artifact_ids:
            raise ValueError(f"duplicate reproducibility artifact id: {artifact.artifact_id}")
        seen_artifact_ids.add(artifact.artifact_id)
        normalized_artifacts.append(artifact)

    return tuple(sorted(normalized_artifacts, key=lambda item: item.artifact_id))


def _normalize_unique_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized_values = _normalize_text_tuple(values, field_name)
    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError(f"duplicate {field_name}")
    return tuple(sorted(normalized_values))


def _normalize_text_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        normalized_values.append(_require_non_empty(value, field_name))
    return tuple(normalized_values)


def _require_non_empty(value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")
    return normalized_value


def _require_aware_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stable_sha256(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()

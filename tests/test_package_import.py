from __future__ import annotations

import ix_blackfox_worldtwin as worldtwin


def test_package_exports_stable_identity() -> None:
    identity = worldtwin.get_package_identity()

    assert identity.project_name == "IX-BlackFox-WorldTwin"
    assert identity.package_name == "ix_blackfox_worldtwin"
    assert identity.version == worldtwin.VERSION
    assert identity.license_name == worldtwin.LICENSE_NAME
    assert identity.research_status == "research-prototype"
    assert "WorldTwin tests possible consequences" in identity.doctrine
    assert "bounded, reviewable evidence" in identity.foundational_law
    assert "governed world-model evidence layer" in identity.public_description


def test_public_api_rejects_overclaims_by_identity() -> None:
    identity = worldtwin.get_package_identity()

    assert "AGI" in identity.prohibited_claims
    assert "production-ready" in identity.prohibited_claims
    assert "certified" in identity.prohibited_claims
    assert "real-world predictive authority" in identity.prohibited_claims

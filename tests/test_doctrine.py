from __future__ import annotations

import ix_blackfox_worldtwin as worldtwin


def test_triad_roles_define_distinct_boundaries() -> None:
    roles = worldtwin.get_triad_roles()

    assert len(roles) == 3
    assert roles[0].component == "IX-BlackFox-Cognition"
    assert roles[1].component == "IX-BlackFox-WorldTwin"
    assert roles[2].component == "IX-BlackFox"
    assert "tests bounded scenarios" in roles[1].responsibility
    assert "does not authorize action" in roles[1].boundary
    assert "does not execute actions" in roles[0].boundary
    assert "without human authorization" in roles[2].boundary


def test_worldtwin_foundational_rules_prevent_prediction_authority() -> None:
    rules = worldtwin.get_worldtwin_foundational_rules()

    assert "Predictions are evidence, not authority." in rules
    assert "Simulated outcomes must remain accountable to observed outcomes." in rules
    assert any("WorldTwin" in rule and "may not execute action" in rule for rule in rules)


def test_claim_boundary_rules_detect_overclaim_language() -> None:
    text = "This AGI system is production-ready, certified, and defense-approved."

    violations = worldtwin.find_claim_boundary_violations(text)
    rule_ids = {violation.rule_id for violation in violations}

    assert rule_ids == {
        "no-agi-claim",
        "no-production-readiness",
        "no-certification",
        "no-defense-affiliation",
    }
    assert worldtwin.is_claim_language_allowed(text) is False


def test_claim_boundary_rules_accept_bounded_language() -> None:
    text = (
        "IX-BlackFox-WorldTwin is a governed world-model evidence layer that "
        "produces human-reviewable execution evidence."
    )

    assert worldtwin.find_claim_boundary_violations(text) == ()
    assert worldtwin.is_claim_language_allowed(text) is True


def test_doctrine_summary_matches_canonical_public_api() -> None:
    summary = worldtwin.render_doctrine_summary()

    assert summary == worldtwin.CANONICAL_DOCTRINE
    assert "WorldTwin tests possible consequences" in summary
    assert "humans authorize" in summary
    assert "evidence decides trust" in summary


def test_claim_boundary_violations_include_safer_language() -> None:
    violations = worldtwin.find_claim_boundary_violations("autonomous authority")

    assert len(violations) == 1
    violation = violations[0]
    assert violation.rule_id == "no-autonomous-authority"
    assert violation.matched_phrase == "autonomous authority"
    assert "must not imply authority" in violation.reason
    assert violation.safer_language == "human-reviewable execution evidence"

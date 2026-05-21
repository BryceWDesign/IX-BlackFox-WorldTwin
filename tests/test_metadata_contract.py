from __future__ import annotations

import ix_blackfox_worldtwin as worldtwin


def test_github_description_is_external_reader_safe() -> None:
    description = worldtwin.get_github_description()

    assert len(description) <= worldtwin.GITHUB_DESCRIPTION_LIMIT
    assert worldtwin.get_external_description_issues(description) == ()
    assert "Cognition" not in description
    assert "AGI" not in description
    assert "human-reviewable execution evidence" in description


def test_github_topics_are_exactly_twenty_and_stable() -> None:
    topics = worldtwin.get_github_topics()

    assert len(topics) == 20
    assert len(set(topics)) == 20
    assert topics[0] == "ai-agents"
    assert "world-model" in topics
    assert "assumption-ledger" in topics
    assert "reality-delta" in topics
    assert "decision-support" in topics


def test_external_description_validator_blocks_insider_or_overclaim_terms() -> None:
    issues = worldtwin.get_external_description_issues(
        "IX-BlackFox-Cognition AGI production-ready certified simulator"
    )

    assert "description contains prohibited or insider term: IX-BlackFox-Cognition" in issues
    assert "description contains prohibited or insider term: AGI" in issues
    assert "description contains prohibited or insider term: production-ready" in issues
    assert "description contains prohibited or insider term: certified" in issues


def test_external_description_validator_blocks_over_length_description() -> None:
    issues = worldtwin.get_external_description_issues("x" * 300)

    assert issues == ("description exceeds GitHub description limit",)


def test_prohibited_claim_check_is_case_insensitive_and_exact() -> None:
    assert worldtwin.is_prohibited_claim("agi") is True
    assert worldtwin.is_prohibited_claim("Production-Ready") is True
    assert worldtwin.is_prohibited_claim("bounded simulation evidence") is False


def test_package_identity_contains_repository_metadata() -> None:
    identity = worldtwin.get_package_identity()

    assert identity.github_description == worldtwin.GITHUB_DESCRIPTION
    assert identity.github_description_limit == 299
    assert identity.github_topics == worldtwin.GITHUB_TOPICS
    assert identity.repository_url.endswith("/IX-BlackFox-WorldTwin")
    assert "linkedin.com/in/brycewdesign" in identity.commercial_licensing_url

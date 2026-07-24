"""Tests for version-one deterministic sponsor eligibility rules."""

import pytest

from services.sponsor_eligibility import (
    AudienceAgeContext,
    EligibilityEvidenceSource,
    EligibilityFacts,
)
from services.sponsor_eligibility_rules_v1 import (
    MINOR_RESTRICTED_INDUSTRIES,
    RULE_VERSION,
    SponsorEligibilityRulesV1,
)


def make_facts(audience: str, **overrides) -> EligibilityFacts:
    values = {
        "mission": "Provide community education and enrichment.",
        "location": "Durham, NC",
        "initiative_name": "Community Program",
        "audience": audience,
    }
    values.update(overrides)
    return EligibilityFacts(**values)


@pytest.mark.parametrize(
    ("audience", "expected_context"),
    [
        ("Children ages 8 to 12", AudienceAgeContext.CHILDREN),
        ("Youth and high school students", AudienceAgeContext.YOUTH),
        (
            "Families and community members of all ages",
            AudienceAgeContext.MIXED_WITH_MINORS,
        ),
    ],
)
def test_minor_audiences_receive_all_strict_exclusions(
    audience,
    expected_context,
):
    context, audits = SponsorEligibilityRulesV1().execute(
        make_facts(audience)
    )

    assert context.age_context is expected_context
    assert {
        item.industry_code
        for item in context.exclusions
    } == {
        code
        for code, _ in MINOR_RESTRICTED_INDUSTRIES
    }
    assert all(
        item.rule_id == "minor_audience_industry_exclusions"
        for item in context.exclusions
    )
    assert all(
        item.reason_code == "minor_audience_age_safety"
        for item in context.exclusions
    )
    assert audits


def test_clearly_adult_only_audience_avoids_youth_exclusions():
    context, _ = SponsorEligibilityRulesV1().execute(
        make_facts("Adults 21+ attending a professional networking event")
    )

    assert context.age_context is AudienceAgeContext.ADULT_ONLY
    assert context.exclusions == []
    assert context.blocking_reasons == []


def test_unclear_age_context_blocks_research():
    context, audits = SponsorEligibilityRulesV1().execute(
        make_facts("Local residents and community partners")
    )

    assert context.age_context is AudienceAgeContext.UNCLEAR
    assert "audience_age_context_required" in context.blocking_reasons
    assert "audience_age_context" in context.missing_information
    assert any(
        audit.rule_id == "unclear_age_research_block"
        and audit.outcome == "research_blocked"
        for audit in audits
    )


def test_future_user_restrictions_create_auditable_exclusions():
    context, audits = SponsorEligibilityRulesV1().execute(
        make_facts(
            "Adults 21+",
            explicit_restrictions=["Payday Lending"],
        )
    )

    exclusion = next(
        item
        for item in context.exclusions
        if item.industry_code == "payday-lending"
    )
    assert exclusion.rule_id == "explicit_user_restrictions"
    assert exclusion.reason_code == "user_provided_restriction"
    assert exclusion.source is EligibilityEvidenceSource.USER_RESTRICTION
    assert any(
        audit.rule_id == "explicit_user_restrictions"
        and audit.outcome == "excluded_industries=1"
        for audit in audits
    )


def test_every_executed_rule_has_complete_audit_data():
    ruleset = SponsorEligibilityRulesV1()
    _, audits = ruleset.execute(make_facts("Youth ages 13 to 17"))

    assert len(audits) == len(ruleset.rules)
    for audit in audits:
        assert audit.rule_id
        assert audit.rule_version == RULE_VERSION
        assert audit.reason_code
        assert audit.evidence_sources
        assert audit.outcome

"""Tests for version-one deterministic sponsor eligibility rules."""

import pytest

from services.sponsor_eligibility import (
    AudienceAgeContext,
    EligibilityEvidenceSource,
    EligibilityFacts,
)
from services.sponsor_eligibility_rules_v1 import RULE_VERSION, SponsorEligibilityRulesV1


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
def test_minor_audiences_do_not_create_automatic_exclusions(
    audience,
    expected_context,
):
    context, audits = SponsorEligibilityRulesV1().execute(
        make_facts(audience)
    )

    assert context.age_context is expected_context
    assert context.exclusions == []
    assert audits


def test_clearly_adult_only_audience_avoids_youth_exclusions():
    context, _ = SponsorEligibilityRulesV1().execute(
        make_facts("Adults 21+ attending a professional networking event")
    )

    assert context.age_context is AudienceAgeContext.ADULT_ONLY
    assert context.exclusions == []
    assert context.blocking_reasons == []


def test_unclear_age_context_does_not_block_research():
    context, audits = SponsorEligibilityRulesV1().execute(
        make_facts("Local residents and community partners")
    )

    assert context.age_context is AudienceAgeContext.UNCLEAR
    assert context.blocking_reasons == []
    assert context.missing_information == []


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

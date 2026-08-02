"""Tests for the deterministic Marsha AI Sponsor Eligibility Engine."""

from types import SimpleNamespace

import pytest

from services.sponsor_eligibility import (
    AudienceAgeContext,
    EligibilityConfidence,
    EligibilityFacts,
    EligibilityStatus,
)
from services.sponsor_eligibility_engine import (
    SponsorEligibilityEngine,
    generate_sponsor_eligibility_analysis,
    normalize_eligibility_facts,
)


def test_normalize_eligibility_facts_uses_existing_inputs():
    organization = SimpleNamespace(
        organization_type="Conference",
        mission="Support women entrepreneurs.",
        location="Atlanta, GA",
    )
    initiative = SimpleNamespace(
        name="Leadership Summit",
        audience="Adult professionals 21+",
        needs="Financial and technology sponsors",
        goals="Expand professional education",
        fundraising_target="$50,000",
        deadline=None,
    )
    analysis = SimpleNamespace(
        target_audiences=["Women entrepreneurs", "Business leaders"],
        risks_or_gaps=["Attendance is unconfirmed"],
    )
    strategy = SimpleNamespace(
        partnership_principles=["Prioritize mission alignment"],
        sponsor_benefits=["Professional audience engagement"],
    )
    categories = SimpleNamespace(
        categories=[
            SimpleNamespace(
                slug="technology",
                category="Technology",
                ideal_sponsor_profile="Technology firms serving businesses",
            )
        ]
    )
    assets = SimpleNamespace(
        assets=[SimpleNamespace(name="Education Partner")]
    )

    facts = normalize_eligibility_facts(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        assets,
    )

    assert facts.organization_type == "Conference"
    assert facts.audience == "Adult professionals 21+"
    assert facts.analyzed_target_audiences == [
        "Women entrepreneurs",
        "Business leaders",
    ]
    assert facts.category_slugs == ["technology"]
    assert facts.asset_names == ["Education Partner"]


def test_minor_audience_context_does_not_impose_category_exclusions():
    facts = EligibilityFacts(
        organization_type="School",
        mission="Support student education.",
        location="Durham, NC",
        initiative_name="Youth Education Program",
        audience="Middle and high school students",
        needs="Program sponsors",
        goals="Expand student access",
        category_names=["Alcohol and Beverage Brands"],
        category_ideal_profiles=[
            "Consumer brands seeking student visibility"
        ],
    )

    result = SponsorEligibilityEngine().evaluate(facts)

    assert result.audience_age_context is AudienceAgeContext.YOUTH
    assert result.eligibility_status is EligibilityStatus.ELIGIBLE
    assert result.research_blocked is False
    assert result.excluded_industries == []
    assert result.applied_rules
    assert result.exclusion_sources == []


def test_minor_audience_does_not_override_user_permitted_category():
    facts = EligibilityFacts(
        mission="Serve local youth.",
        location="Durham, NC",
        initiative_name="Youth Festival",
        audience="Children and families",
        category_names=["Alcohol"],
        category_ideal_profiles=[
            "Alcohol brands seeking event visibility"
        ],
    )

    result = SponsorEligibilityEngine().evaluate(facts)

    assert "Alcohol brands seeking event visibility" in (
        result.preferred_sponsor_characteristics
    )
    assert result.excluded_industries == []


def test_unclear_age_is_low_confidence_and_allows_research():
    facts = EligibilityFacts(
        mission="Serve the local community.",
        location="Durham, NC",
        initiative_name="Community Initiative",
        audience="Community members",
    )

    result = SponsorEligibilityEngine().evaluate(facts)

    assert result.audience_age_context is AudienceAgeContext.UNCLEAR
    assert result.confidence is EligibilityConfidence.LOW
    assert result.eligibility_status is EligibilityStatus.ELIGIBLE
    assert result.research_blocked is False
    assert result.blocking_reasons == []


@pytest.mark.parametrize(
    "age_context",
    [
        AudienceAgeContext.UNCLEAR,
        AudienceAgeContext.MIXED_WITH_MINORS,
        AudienceAgeContext.YOUTH,
    ],
)
def test_user_selected_age_context_never_blocks_general_research(age_context):
    result = SponsorEligibilityEngine().evaluate(EligibilityFacts(
        mission="Serve the local community.",
        location="Durham, NC",
        initiative_name="Community Initiative",
        audience="Community members",
        audience_age_preference=age_context,
    ))

    assert result.audience_age_context is age_context
    assert result.research_blocked is False
    assert result.excluded_industries == []


def test_clearly_adult_only_analysis_has_no_blanket_youth_exclusions():
    facts = EligibilityFacts(
        mission="Support professional development.",
        location="Charlotte, NC",
        initiative_name="Executive Leadership Dinner",
        audience="Adults 21 and older",
    )

    result = SponsorEligibilityEngine().evaluate(facts)

    assert result.audience_age_context is AudienceAgeContext.ADULT_ONLY
    assert result.eligibility_status is EligibilityStatus.ELIGIBLE
    assert result.research_blocked is False
    assert result.excluded_industries == []


def test_generate_analysis_requires_no_database_context():
    result = generate_sponsor_eligibility_analysis(
        SimpleNamespace(
            organization_type="Community Group",
            mission="Support local families.",
            location="Raleigh, NC",
        ),
        SimpleNamespace(
            name="Family Festival",
            audience="Families and children",
            needs="Community sponsors",
            goals="Increase program access",
            fundraising_target="",
            deadline=None,
        ),
        SimpleNamespace(
            target_audiences=["Families"],
            risks_or_gaps=[],
        ),
        SimpleNamespace(
            partnership_principles=[],
            sponsor_benefits=[],
        ),
        SimpleNamespace(categories=[]),
        SimpleNamespace(assets=[]),
    )

    assert result.audience_age_context is (
        AudienceAgeContext.MIXED_WITH_MINORS
    )


def test_generate_analysis_uses_saved_user_preferences():
    result = generate_sponsor_eligibility_analysis(
        SimpleNamespace(
            organization_type="Community Group",
            mission="Support local families.",
            location="Raleigh, NC",
        ),
        SimpleNamespace(
            name="Family Festival",
            audience="Audience description without an explicit age",
            audience_age_context="youth",
            sponsor_category_exclusions_json=(
                '["Alcohol and breweries", "Payday lending"]'
            ),
            needs="Community sponsors",
            goals="Increase program access",
            fundraising_target="",
            deadline=None,
        ),
        SimpleNamespace(target_audiences=[], risks_or_gaps=[]),
        SimpleNamespace(partnership_principles=[], sponsor_benefits=[]),
        SimpleNamespace(categories=[]),
        SimpleNamespace(assets=[]),
    )

    assert result.audience_age_context is AudienceAgeContext.YOUTH
    assert {
        item.industry_label for item in result.excluded_industries
    } == {"Alcohol and breweries", "Payday lending"}
    assert all(
        item.reason_code == "user_provided_restriction"
        for item in result.excluded_industries
    )

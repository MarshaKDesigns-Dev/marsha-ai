from types import SimpleNamespace

from services.sponsorship_context import (
    build_sponsorship_context,
    format_sponsorship_context,
    geographic_instruction,
    mapped_industries,
    parse_multiline,
    validate_needs,
)


def test_needs_taxonomy_rejects_unknown_values():
    assert validate_needs(
        ["Cash Sponsorship", "Transportation", "Invented"]
    ) == ["Cash Sponsorship", "Transportation"]


def test_multiline_values_are_cleaned_and_deduplicated():
    assert parse_multiline("Acme Inc.\n acme inc. \nLocal Bank") == [
        "Acme Inc.",
        "Local Bank",
    ]


def test_industry_mapping_is_deterministic():
    assert mapped_industries(["Transportation", "Hotels"]) == [
        "transportation",
        "automotive",
        "mobility",
        "logistics",
        "hospitality",
        "lodging",
        "tourism",
    ]


def test_radius_instruction_uses_organization_location():
    organization = SimpleNamespace(location="Durham, NC")
    initiative = SimpleNamespace(
        geographic_scope="Radius",
        geographic_radius_miles=25,
    )

    assert geographic_instruction(initiative, organization) == (
        "Within 25 miles of Durham, NC"
    )


def test_shared_context_includes_needs_and_relationship_rules():
    organization = SimpleNamespace(
        mission="Support youth leaders",
        organization_type="Nonprofit",
        location="Durham, NC",
        current_sponsors_json='["Current Co"]',
        existing_relationships_json='["Partner Co"]',
        businesses_already_contacted_json='["Contacted Co"]',
        businesses_never_contact_json='["Blocked Co"]',
    )
    initiative = SimpleNamespace(
        sponsorship_needs_json='["Scholarships", "Transportation"]',
        sponsorship_needs_other="",
        sponsorship_needs_notes="Ten scholarships",
        needs="Funding",
        fundraising_target="$20,000",
        desired_sponsor_categories_json='["Education"]',
        geographic_scope="My State",
        geographic_radius_miles=None,
        dream_sponsors_json='["Dream Co"]',
        audience="Students ages 14-18",
        strategy_top_priorities="Scholarships, visibility, relationships",
        strategy_priority_sponsors="Local Bank",
        strategy_success_beyond_fundraising="Stronger alumni engagement",
        strategy_concerns_constraints="Volunteer capacity",
        audience_age_context="mixed_with_minors",
        sponsor_category_exclusions_json=(
            '["Alcohol and breweries", "Payday lending"]'
        ),
    )

    context = build_sponsorship_context(organization, initiative)

    assert context["structured_needs"] == [
        "Scholarships",
        "Transportation",
    ]
    assert "workforce development" in context["industry_mapping"]
    assert context["dream_sponsors"] == ["Dream Co"]
    assert context["businesses_never_contact"] == ["Blocked Co"]
    assert context["strategy_top_priorities"] == (
        "Scholarships, visibility, relationships"
    )
    assert context["strategy_priority_sponsors"] == "Local Bank"
    assert context["strategy_success_beyond_fundraising"] == (
        "Stronger alumni engagement"
    )
    assert context["strategy_concerns_constraints"] == "Volunteer capacity"
    assert context["audience_age_context"] == "mixed_with_minors"
    assert context["sponsor_category_exclusions"] == [
        "Alcohol and breweries",
        "Payday lending",
    ]
    prompt = format_sponsorship_context(organization, initiative)
    assert "User-selected audience age context: mixed_with_minors" in prompt
    assert "Alcohol and breweries" in prompt

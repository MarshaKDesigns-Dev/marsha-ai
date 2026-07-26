from types import SimpleNamespace

from services.sponsor_preferences import (
    evaluate_sponsor_preference,
    normalized_company_name,
)


def records(**overrides):
    organization = SimpleNamespace(
        mission="Serve local families",
        organization_type="Nonprofit",
        location="Durham, NC",
        current_sponsors_json='["Current Sponsor LLC"]',
        existing_relationships_json='["Relationship Company"]',
        businesses_already_contacted_json='["Contacted Company"]',
        businesses_never_contact_json='["Blocked Company, Inc."]',
    )
    initiative = SimpleNamespace(
        sponsorship_needs_json='["Cash Sponsorship"]',
        sponsorship_needs_other="",
        sponsorship_needs_notes="",
        needs="",
        fundraising_target="$10,000",
        desired_sponsor_categories_json="[]",
        geographic_scope="My City",
        geographic_radius_miles=None,
        dream_sponsors_json="[]",
        audience="Adults 21+",
    )
    for key, value in overrides.items():
        setattr(organization, key, value)
    return organization, initiative


def test_exact_normalization_ignores_legal_suffix_and_punctuation():
    assert normalized_company_name("Blocked Company, Inc.") == (
        normalized_company_name("Blocked Company")
    )


def test_never_contact_is_deterministically_excluded_with_reason():
    organization, initiative = records()

    decision = evaluate_sponsor_preference(
        "Blocked Company",
        organization,
        initiative,
    )

    assert decision.allowed is False
    assert decision.reason_code == "never_contact"
    assert decision.matched_name == "Blocked Company, Inc."


def test_similar_name_is_not_fuzzy_excluded():
    organization, initiative = records()

    decision = evaluate_sponsor_preference(
        "Blocked Company Foundation",
        organization,
        initiative,
    )

    assert decision.allowed is True

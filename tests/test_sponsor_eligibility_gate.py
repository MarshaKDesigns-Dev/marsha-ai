"""Tests for deterministic category research gating."""

from types import SimpleNamespace

import pytest

from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_eligibility_gate import evaluate_category_research


def _analysis(audience, *, category_name="Healthcare", restrictions=()):
    return SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support community education.",
            location="Durham, NC",
            initiative_name="Community Program",
            audience=audience,
            category_names=[category_name],
            category_ideal_profiles=[
                "A strongly aligned sponsor recommended by AI"
            ],
            explicit_restrictions=list(restrictions),
        )
    )


def test_allowed_category_can_proceed_to_research():
    decision = evaluate_category_research(
        _analysis("Adults 21 and older"),
        SimpleNamespace(slug="healthcare", category="Healthcare"),
    )

    assert decision.allowed is True
    assert decision.reason is None


def test_user_excluded_category_is_blocked():
    decision = evaluate_category_research(
        _analysis(
            "Middle school students",
            category_name="Alcohol Brands",
            restrictions=["Alcohol and breweries"],
        ),
        SimpleNamespace(
            slug="alcohol-brands",
            category="Alcohol and Beverage Brands",
        ),
    )

    assert decision.allowed is False
    assert "Alcohol" in decision.reason


def test_unclear_age_allows_general_research():
    decision = evaluate_category_research(
        _analysis("Community members"),
        SimpleNamespace(slug="healthcare", category="Healthcare"),
    )

    assert decision.allowed is True


def test_user_exclusion_overrides_positive_ai_recommendation():
    analysis = _analysis(
        "Children and families",
        category_name="Alcohol Brands",
        restrictions=["Alcohol and breweries"],
    )
    assert "A strongly aligned sponsor recommended by AI" in (
        analysis.preferred_sponsor_characteristics
    )

    decision = evaluate_category_research(
        analysis,
        SimpleNamespace(slug="alcohol", category="Alcohol Brands"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "user_provided_restriction"


def test_legacy_record_without_eligibility_is_blocked():
    decision = evaluate_category_research(
        None,
        SimpleNamespace(slug="healthcare", category="Healthcare"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "eligibility_analysis_required"


@pytest.mark.parametrize(
    ("restriction", "slug", "category"),
    [
        ("Alcohol and breweries", "breweries", "Craft Breweries"),
        ("Cannabis", "cannabis", "Cannabis Companies"),
        ("Gambling and casinos", "casinos", "Casinos"),
        ("Tobacco and nicotine", "nicotine", "Nicotine Products"),
        ("Adult entertainment or adult content", "adult-content", "Adult Content"),
        ("Firearms or weapons", "firearms", "Firearms Manufacturers"),
        ("Political organizations", "political", "Political Organizations"),
        ("Religious organizations", "religious", "Religious Organizations"),
    ],
)
def test_each_user_category_exclusion_is_enforced_independently(
    restriction, slug, category,
):
    decision = evaluate_category_research(
        _analysis(
            "Adults and minors",
            category_name=category,
            restrictions=[restriction],
        ),
        SimpleNamespace(slug=slug, category=category),
    )

    assert decision.allowed is False
    assert decision.reason_code == "user_provided_restriction"


def test_minors_do_not_override_user_permission_for_alcohol():
    decision = evaluate_category_research(
        _analysis("Minors primarily", category_name="Alcohol Brands"),
        SimpleNamespace(slug="alcohol", category="Alcohol Brands"),
    )

    assert decision.allowed is True

"""Tests for deterministic category research gating."""

from types import SimpleNamespace

from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_eligibility_gate import evaluate_category_research


def _analysis(audience, *, category_name="Healthcare"):
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
        )
    )


def test_allowed_category_can_proceed_to_research():
    decision = evaluate_category_research(
        _analysis("Adults 21 and older"),
        SimpleNamespace(slug="healthcare", category="Healthcare"),
    )

    assert decision.allowed is True
    assert decision.reason is None


def test_excluded_category_is_blocked():
    decision = evaluate_category_research(
        _analysis("Middle school students", category_name="Alcohol Brands"),
        SimpleNamespace(
            slug="alcohol-brands",
            category="Alcohol and Beverage Brands",
        ),
    )

    assert decision.allowed is False
    assert "Alcohol" in decision.reason


def test_unclear_age_blocks_research():
    decision = evaluate_category_research(
        _analysis("Community members"),
        SimpleNamespace(slug="healthcare", category="Healthcare"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "audience_age_context_required"


def test_deterministic_exclusion_overrides_positive_ai_recommendation():
    analysis = _analysis(
        "Children and families",
        category_name="Alcohol Brands",
    )
    assert "A strongly aligned sponsor recommended by AI" in (
        analysis.preferred_sponsor_characteristics
    )

    decision = evaluate_category_research(
        analysis,
        SimpleNamespace(slug="alcohol", category="Alcohol Brands"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "minor_audience_age_safety"


def test_legacy_record_without_eligibility_is_blocked():
    decision = evaluate_category_research(
        None,
        SimpleNamespace(slug="healthcare", category="Healthcare"),
    )

    assert decision.allowed is False
    assert decision.reason_code == "eligibility_analysis_required"

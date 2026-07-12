from types import SimpleNamespace

import pytest

from services.organization_analysis import OrganizationAnalysis
from services.sponsorship_strategy import (
    SponsorshipObjective,
    SponsorshipStrategy,
)
from services.sponsor_categories import (
    SponsorCategoryGenerationError,
    SponsorCategoryRecommendation,
    SponsorCategorySet,
    build_category_prompt,
    generate_sponsor_categories,
)


class FakeResponse:
    def __init__(self, parsed):
        self.output_parsed = parsed


class FakeResponsesAPI:
    def __init__(self, parsed=None, error=None):
        self._parsed = parsed
        self._error = error
        self.last_kwargs = None

    def parse(self, **kwargs):
        self.last_kwargs = kwargs

        if self._error:
            raise self._error

        return FakeResponse(self._parsed)


class FakeClient:
    def __init__(self, parsed=None, error=None):
        self.responses = FakeResponsesAPI(
            parsed=parsed,
            error=error,
        )


@pytest.fixture
def organization():
    return SimpleNamespace(
        name="Community Arts Center",
        organization_type="Nonprofit",
        location="Durham, NC",
        mission="Affordable arts education.",
    )


@pytest.fixture
def initiative():
    return SimpleNamespace(
        name="Summer Arts Festival",
        fundraising_target="$50,000",
        audience="Families",
        needs="Sponsors",
        goals="Expand programming",
    )


@pytest.fixture
def analysis():
    return OrganizationAnalysis(
        organization_summary="Community arts nonprofit serving local residents through education.",
        initiative_summary="Annual arts festival supporting community engagement.",
        mission_strengths=["Arts education"],
        community_impact=["Community engagement"],
        target_audiences=["Families"],
        sponsorship_objectives=["Increase sponsorship revenue"],
        sponsor_value_proposition="Sponsors gain meaningful community visibility.",
        strategy_direction="Focus on organizations investing in education and community.",
        risks_or_gaps=[],
    )


@pytest.fixture
def strategy():
    return SponsorshipStrategy(
        positioning_statement="Position the festival as a community-centered arts experience.",
        strategic_theme="Community Arts",
        recommended_approach="Develop long-term mission-aligned sponsorships.",
        objectives=[
            SponsorshipObjective(
                objective="Increase sponsorship revenue",
                rationale="Supports expanded programming.",
                success_measure="Revenue target achieved",
            )
        ],
        sponsor_benefits=[
            "Community visibility",
        ],
        partnership_principles=[
            "Mission alignment",
        ],
        activation_priorities=[
            "Community engagement",
        ],
        measurement_priorities=[
            "Sponsor retention",
        ],
        recommended_next_steps=[
            "Identify sponsor categories",
        ],
        risks_or_constraints=[],
    )


@pytest.fixture
def category_set():
    return SponsorCategorySet(
        categories=[
            SponsorCategoryRecommendation(
                slug="financial-institutions",
                category="Financial Institutions",
                fit="Banks often invest in community education and local events.",
                score=95,
                priority=1,
                ideal_sponsor_profile="Regional banks with community investment programs.",
                research_direction="Identify banks with charitable foundations.",
            ),
            SponsorCategoryRecommendation(
                slug="healthcare",
                category="Healthcare",
                fit="Healthcare organizations often support healthy communities.",
                score=90,
                priority=2,
                ideal_sponsor_profile="Regional healthcare providers.",
                research_direction="Research hospitals and healthcare systems.",
            ),
            SponsorCategoryRecommendation(
                slug="utilities",
                category="Utilities",
                fit="Utility companies frequently sponsor community initiatives.",
                score=85,
                priority=3,
                ideal_sponsor_profile="Electric and utility providers.",
                research_direction="Review community investment reports.",
            ),
        ]
    )


def test_build_prompt_contains_context(
    organization,
    initiative,
    analysis,
    strategy,
):
    prompt = build_category_prompt(
        organization,
        initiative,
        analysis,
        strategy,
    )

    assert "Community Arts Center" in prompt
    assert "Summer Arts Festival" in prompt
    assert analysis.organization_summary in prompt
    assert strategy.positioning_statement in prompt


def test_missing_organization_name_raises(
    initiative,
    analysis,
    strategy,
):
    organization = SimpleNamespace(name="")

    with pytest.raises(SponsorCategoryGenerationError):
        build_category_prompt(
            organization,
            initiative,
            analysis,
            strategy,
        )


def test_generate_categories_returns_valid_model(
    organization,
    initiative,
    analysis,
    strategy,
    category_set,
):
    client = FakeClient(parsed=category_set)

    result = generate_sponsor_categories(
        organization,
        initiative,
        analysis,
        strategy,
        client=client,
        model="test-model",
    )

    assert isinstance(result, SponsorCategorySet)
    assert len(result.categories) == 3
    assert result.categories[0].priority == 1
    assert client.responses.last_kwargs["model"] == "test-model"


def test_missing_response_raises(
    organization,
    initiative,
    analysis,
    strategy,
):
    client = FakeClient(parsed=None)

    with pytest.raises(SponsorCategoryGenerationError):
        generate_sponsor_categories(
            organization,
            initiative,
            analysis,
            strategy,
            client=client,
        )


def test_api_failure_raises(
    organization,
    initiative,
    analysis,
    strategy,
):
    client = FakeClient(error=RuntimeError("API Failure"))

    with pytest.raises(SponsorCategoryGenerationError):
        generate_sponsor_categories(
            organization,
            initiative,
            analysis,
            strategy,
            client=client,
        )
        
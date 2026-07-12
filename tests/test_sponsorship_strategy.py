from types import SimpleNamespace

import pytest

from services.organization_analysis import OrganizationAnalysis
from services.sponsorship_strategy import (
    SponsorshipObjective,
    SponsorshipStrategy,
    SponsorshipStrategyError,
    build_strategy_prompt,
    generate_sponsorship_strategy,
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
        mission=(
            "Provide affordable arts education and community programming."
        ),
        website="https://example.org",
    )


@pytest.fixture
def initiative():
    return SimpleNamespace(
        name="Summer Arts Festival",
        fundraising_target="$50,000",
        deadline=None,
        audience="Families, students, artists, and local residents",
        needs="Financial sponsors and in-kind community partners",
        goals="Expand programming and increase community participation",
    )


@pytest.fixture
def analysis():
    return OrganizationAnalysis(
        organization_summary=(
            "Community Arts Center is a nonprofit that provides affordable "
            "arts education and public programming for local residents."
        ),
        initiative_summary=(
            "The Summer Arts Festival is a community event intended to "
            "expand arts participation and support future programming."
        ),
        mission_strengths=[
            "Accessible arts education",
            "Strong community participation",
        ],
        community_impact=[
            "Provides affordable cultural programming",
            "Creates opportunities for local artists and students",
        ],
        target_audiences=[
            "Families",
            "Students",
            "Local artists",
            "Community residents",
        ],
        sponsorship_objectives=[
            "Secure financial support for festival delivery",
            "Build long-term community business partnerships",
        ],
        sponsor_value_proposition=(
            "Sponsors can align with accessible arts education while gaining "
            "credible visibility among community-focused audiences."
        ),
        strategy_direction=(
            "Prioritize regional organizations that value education, arts, "
            "community development, and local engagement."
        ),
        risks_or_gaps=[
            "Confirmed attendance projections are not available",
            "Detailed audience demographics have not been provided",
        ],
    )


@pytest.fixture
def strategy():
    return SponsorshipStrategy(
        positioning_statement=(
            "Position the Summer Arts Festival as a community-centered arts "
            "initiative that connects sponsors with families, students, "
            "artists, and local residents."
        ),
        strategic_theme=(
            "Accessible arts education and community connection"
        ),
        recommended_approach=(
            "Build partnerships with organizations whose community investment "
            "goals align with arts access, education, family engagement, and "
            "local economic participation."
        ),
        objectives=[
            SponsorshipObjective(
                objective=(
                    "Secure sufficient financial support for festival delivery"
                ),
                rationale=(
                    "Financial sponsorship will help the organization expand "
                    "programming without reducing community accessibility."
                ),
                success_measure=(
                    "Track committed sponsorship revenue against the "
                    "initiative fundraising target."
                ),
            )
        ],
        sponsor_benefits=[
            "Community visibility",
            "Association with accessible arts education",
            "Opportunities for audience engagement",
        ],
        partnership_principles=[
            "Prioritize mission and audience alignment",
            "Avoid promising unsupported reach or outcomes",
        ],
        activation_priorities=[
            "Community-facing festival participation",
            "Educational or family-focused engagement",
        ],
        measurement_priorities=[
            "Sponsorship revenue committed",
            "Sponsor participation delivered",
            "Audience engagement evidence collected",
        ],
        recommended_next_steps=[
            "Confirm audience and attendance information",
            "Define sponsorship assets",
            "Identify aligned sponsor categories",
        ],
        risks_or_constraints=[
            "Attendance projections are not yet confirmed",
        ],
    )


def test_build_strategy_prompt_contains_required_context(
    organization,
    initiative,
    analysis,
):
    prompt = build_strategy_prompt(
        organization,
        initiative,
        analysis,
    )

    assert "Community Arts Center" in prompt
    assert "Summer Arts Festival" in prompt
    assert analysis.organization_summary in prompt
    assert analysis.sponsor_value_proposition in prompt
    assert "Confirmed attendance projections are not available" in prompt


def test_missing_organization_name_raises(
    initiative,
    analysis,
):
    organization = SimpleNamespace(name="")

    with pytest.raises(
        SponsorshipStrategyError,
        match="Organization name is required",
    ):
        build_strategy_prompt(
            organization,
            initiative,
            analysis,
        )


def test_missing_initiative_name_raises(
    organization,
    analysis,
):
    initiative = SimpleNamespace(name="")

    with pytest.raises(
        SponsorshipStrategyError,
        match="initiative name is required",
    ):
        build_strategy_prompt(
            organization,
            initiative,
            analysis,
        )


def test_invalid_analysis_raises(
    organization,
    initiative,
):
    invalid_analysis = {
        "organization_summary": "Too short",
    }

    with pytest.raises(
        SponsorshipStrategyError,
        match="valid organization analysis is required",
    ):
        build_strategy_prompt(
            organization,
            initiative,
            invalid_analysis,
        )


def test_generate_strategy_returns_valid_model(
    organization,
    initiative,
    analysis,
    strategy,
):
    client = FakeClient(parsed=strategy)

    result = generate_sponsorship_strategy(
        organization,
        initiative,
        analysis,
        client=client,
        model="test-model",
    )

    assert isinstance(result, SponsorshipStrategy)
    assert result.strategic_theme == (
        "Accessible arts education and community connection"
    )
    assert len(result.objectives) == 1
    assert client.responses.last_kwargs["model"] == "test-model"
    assert client.responses.last_kwargs["text_format"] is SponsorshipStrategy


def test_missing_structured_response_raises(
    organization,
    initiative,
    analysis,
):
    client = FakeClient(parsed=None)

    with pytest.raises(
        SponsorshipStrategyError,
        match="no structured sponsorship strategy",
    ):
        generate_sponsorship_strategy(
            organization,
            initiative,
            analysis,
            client=client,
        )


def test_api_failure_raises_service_error(
    organization,
    initiative,
    analysis,
):
    client = FakeClient(
        error=RuntimeError("Temporary API failure"),
    )

    with pytest.raises(
        SponsorshipStrategyError,
        match="request could not be completed",
    ):
        generate_sponsorship_strategy(
            organization,
            initiative,
            analysis,
            client=client,
        )
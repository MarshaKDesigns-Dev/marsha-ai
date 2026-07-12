from types import SimpleNamespace

import pytest

from services.organization_analysis import OrganizationAnalysis
from services.sponsor_categories import (
    SponsorCategoryRecommendation,
    SponsorCategorySet,
)
from services.sponsorship_assets import (
    SponsorshipAssetGenerationError,
    SponsorshipAssetRecommendation,
    SponsorshipAssetSet,
    build_asset_prompt,
    generate_sponsorship_assets,
)
from services.sponsorship_strategy import (
    SponsorshipObjective,
    SponsorshipStrategy,
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
            "Community Arts Center is a nonprofit providing affordable arts "
            "education and public programming for local residents."
        ),
        initiative_summary=(
            "The Summer Arts Festival is a community event intended to "
            "expand arts participation and support future programming."
        ),
        mission_strengths=[
            "Accessible arts education",
            "Community participation",
        ],
        community_impact=[
            "Affordable cultural programming",
            "Opportunities for local artists and students",
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


@pytest.fixture
def categories():
    return SponsorCategorySet(
        categories=[
            SponsorCategoryRecommendation(
                slug="financial-institutions",
                category="Financial Institutions",
                fit=(
                    "Regional financial institutions may align with community "
                    "education, family engagement, and local development."
                ),
                score=95,
                priority=1,
                ideal_sponsor_profile=(
                    "Regional banks and credit unions with community "
                    "investment programs."
                ),
                research_direction=(
                    "Research financial institutions with local giving, "
                    "education, and community development priorities."
                ),
            ),
            SponsorCategoryRecommendation(
                slug="healthcare",
                category="Healthcare",
                fit=(
                    "Healthcare organizations may value community visibility "
                    "and family-focused engagement opportunities."
                ),
                score=90,
                priority=2,
                ideal_sponsor_profile=(
                    "Regional hospitals, clinics, and health systems with "
                    "community outreach programs."
                ),
                research_direction=(
                    "Review healthcare community benefit and outreach programs."
                ),
            ),
            SponsorCategoryRecommendation(
                slug="utilities",
                category="Utilities",
                fit=(
                    "Utility providers often support community initiatives "
                    "and local educational programming."
                ),
                score=85,
                priority=3,
                ideal_sponsor_profile=(
                    "Electric, water, and energy providers with local "
                    "community investment priorities."
                ),
                research_direction=(
                    "Review utility community investment reports and "
                    "regional sponsorship programs."
                ),
            ),
        ]
    )


@pytest.fixture
def asset_set():
    return SponsorshipAssetSet(
        assets=[
            SponsorshipAssetRecommendation(
                name="Community Arts Education Partner",
                description=(
                    "Sponsor recognition connected to accessible arts "
                    "education programming delivered through the festival."
                ),
                sponsor_value=(
                    "Provides visible alignment with education, community "
                    "development, and family-focused programming."
                ),
                audience_value=(
                    "Supports affordable educational experiences for "
                    "families, students, and community residents."
                ),
                delivery_method=(
                    "Recognition in festival materials and during educational "
                    "programming."
                ),
                capacity="Limited",
                exclusivity="Category exclusive",
                measurement_method=(
                    "Document recognition delivered, program participation, "
                    "and sponsor activation completion."
                ),
                recommended_for_categories=[
                    "financial-institutions",
                    "utilities",
                ],
            ),
            SponsorshipAssetRecommendation(
                name="Family Engagement Activity Sponsor",
                description=(
                    "Sponsor-supported interactive activity designed for "
                    "families attending the community arts festival."
                ),
                sponsor_value=(
                    "Creates direct audience engagement and visible community "
                    "participation for the sponsor."
                ),
                audience_value=(
                    "Adds an accessible and engaging experience for families "
                    "and young participants."
                ),
                delivery_method=(
                    "Branded activity area or sponsor-supported educational "
                    "experience."
                ),
                capacity="Multiple",
                exclusivity="Non-exclusive",
                measurement_method=(
                    "Track activity delivery, participation evidence, and "
                    "sponsor recognition completion."
                ),
                recommended_for_categories=[
                    "healthcare",
                    "financial-institutions",
                ],
            ),
            SponsorshipAssetRecommendation(
                name="Community Impact Recognition",
                description=(
                    "Sponsor recognition tied to the festival's broader "
                    "community access and cultural participation goals."
                ),
                sponsor_value=(
                    "Provides credible association with local community impact "
                    "and accessible arts programming."
                ),
                audience_value=(
                    "Helps maintain affordable participation and broader "
                    "community access."
                ),
                delivery_method=(
                    "Recognition in impact communications, event materials, "
                    "and post-event reporting."
                ),
                capacity="Multiple",
                exclusivity="Non-exclusive",
                measurement_method=(
                    "Record sponsor recognition, funded activities, and "
                    "post-event impact documentation."
                ),
                recommended_for_categories=[
                    "utilities",
                    "healthcare",
                ],
            ),
        ]
    )


def test_build_asset_prompt_contains_required_context(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
):
    prompt = build_asset_prompt(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
    )

    assert "Community Arts Center" in prompt
    assert "Summer Arts Festival" in prompt
    assert analysis.organization_summary in prompt
    assert strategy.positioning_statement in prompt
    assert "financial-institutions" in prompt
    assert "Healthcare" in prompt


def test_missing_organization_name_raises(
    initiative,
    analysis,
    strategy,
    categories,
):
    organization = SimpleNamespace(name="")

    with pytest.raises(
        SponsorshipAssetGenerationError,
        match="Organization name is required",
    ):
        build_asset_prompt(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
        )


def test_missing_initiative_name_raises(
    organization,
    analysis,
    strategy,
    categories,
):
    initiative = SimpleNamespace(name="")

    with pytest.raises(
        SponsorshipAssetGenerationError,
        match="initiative name is required",
    ):
        build_asset_prompt(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
        )


def test_invalid_category_set_raises(
    organization,
    initiative,
    analysis,
    strategy,
):
    invalid_categories = {
        "categories": [],
    }

    with pytest.raises(
        SponsorshipAssetGenerationError,
        match="valid sponsor category set is required",
    ):
        build_asset_prompt(
            organization,
            initiative,
            analysis,
            strategy,
            invalid_categories,
        )


def test_generate_assets_returns_valid_model(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    asset_set,
):
    client = FakeClient(parsed=asset_set)

    result = generate_sponsorship_assets(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        client=client,
        model="test-model",
    )

    assert isinstance(result, SponsorshipAssetSet)
    assert len(result.assets) == 3
    assert result.assets[0].name == (
        "Community Arts Education Partner"
    )
    assert client.responses.last_kwargs["model"] == "test-model"
    assert (
        client.responses.last_kwargs["text_format"]
        is SponsorshipAssetSet
    )


def test_missing_structured_response_raises(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
):
    client = FakeClient(parsed=None)

    with pytest.raises(
        SponsorshipAssetGenerationError,
        match="no structured sponsorship assets",
    ):
        generate_sponsorship_assets(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
            client=client,
        )


def test_api_failure_raises_service_error(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
):
    client = FakeClient(
        error=RuntimeError("Temporary API failure"),
    )

    with pytest.raises(
        SponsorshipAssetGenerationError,
        match="request could not be completed",
    ):
        generate_sponsorship_assets(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
            client=client,
        )
        
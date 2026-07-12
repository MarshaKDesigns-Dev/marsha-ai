from types import SimpleNamespace

import pytest

from services.organization_analysis import OrganizationAnalysis
from services.research_priorities import (
    ResearchPriorityGenerationError,
    ResearchPriorityRecommendation,
    ResearchPrioritySet,
    build_research_priority_prompt,
    generate_research_priorities,
)
from services.sponsor_categories import (
    SponsorCategoryRecommendation,
    SponsorCategorySet,
)
from services.sponsorship_assets import (
    SponsorshipAssetRecommendation,
    SponsorshipAssetSet,
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
        mission="Provide affordable arts education.",
    )


@pytest.fixture
def initiative():
    return SimpleNamespace(
        name="Summer Arts Festival",
        fundraising_target="$50,000",
        deadline=None,
        audience="Families",
        needs="Sponsors",
        goals="Expand programming",
    )


@pytest.fixture
def analysis():
    return OrganizationAnalysis(
        organization_summary=(
            "Community Arts Center is a nonprofit serving local residents "
            "through affordable arts education and public programming."
        ),
        initiative_summary=(
            "The Summer Arts Festival is an annual community event designed "
            "to expand access to arts programming."
        ),
        mission_strengths=[
            "Affordable arts education",
            "Community-centered programming",
        ],
        community_impact=[
            "Expands access to cultural programming",
            "Creates opportunities for local participation",
        ],
        target_audiences=[
            "Families",
            "Students",
            "Artists",
            "Community residents",
        ],
        sponsorship_objectives=[
            "Increase sponsorship revenue",
            "Develop long-term community partnerships",
        ],
        sponsor_value_proposition=(
            "Sponsors gain meaningful community visibility while supporting "
            "accessible arts education and local engagement."
        ),
        strategy_direction=(
            "Focus on organizations with demonstrated community investment, "
            "education, and local engagement priorities."
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
            "initiative connecting sponsors with families and residents."
        ),
        strategic_theme=(
            "Accessible arts education and community engagement"
        ),
        recommended_approach=(
            "Develop long-term mission-aligned partnerships with organizations "
            "that value arts education, family participation, and community "
            "engagement."
        ),
        objectives=[
            SponsorshipObjective(
                objective=(
                    "Increase sponsorship revenue for festival programming"
                ),
                rationale=(
                    "Additional sponsorship support will allow the organization "
                    "to expand programming while preserving community access."
                ),
                success_measure=(
                    "Track committed sponsorship revenue against the "
                    "initiative fundraising target."
                ),
            )
        ],
        sponsor_benefits=[
            "Visible alignment with accessible arts education",
            "Meaningful engagement with community audiences",
        ],
        partnership_principles=[
            "Prioritize mission and audience alignment",
            "Avoid unsupported promises about reach or results",
        ],
        activation_priorities=[
            "Community-facing educational engagement",
            "Family-centered festival participation",
        ],
        measurement_priorities=[
            "Committed sponsorship revenue",
            "Delivered sponsor benefits",
            "Documented audience engagement",
        ],
        recommended_next_steps=[
            "Confirm audience and attendance information",
            "Identify qualified sponsor prospects",
        ],
        risks_or_constraints=[
            "Attendance projections have not been confirmed",
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
                    "Regional financial institutions have strong alignment "
                    "with community education and long-term local investment."
                ),
                score=95,
                priority=1,
                ideal_sponsor_profile=(
                    "Regional banks and credit unions with established "
                    "community investment programs."
                ),
                research_direction=(
                    "Research community giving, sponsorship programs, "
                    "and local education initiatives."
                ),
            ),
            SponsorCategoryRecommendation(
                slug="healthcare",
                category="Healthcare",
                fit=(
                    "Healthcare organizations frequently support family "
                    "engagement, community wellness, and local education."
                ),
                score=90,
                priority=2,
                ideal_sponsor_profile=(
                    "Regional hospitals and healthcare systems with active "
                    "community outreach programs."
                ),
                research_direction=(
                    "Review community benefit reports and regional "
                    "outreach initiatives."
                ),
            ),
            SponsorCategoryRecommendation(
                slug="utilities",
                category="Utilities",
                fit=(
                    "Utility providers often invest in community development "
                    "and educational programming throughout their service areas."
                ),
                score=85,
                priority=3,
                ideal_sponsor_profile=(
                    "Electric, water, and energy providers serving "
                    "the local region."
                ),
                research_direction=(
                    "Review annual community investment and "
                    "foundation reports."
                ),
            ),
        ]
    )


@pytest.fixture
def assets():
    return SponsorshipAssetSet(
        assets=[
            SponsorshipAssetRecommendation(
                name="Education Partner",
                description=(
                    "Support educational programming delivered through the "
                    "Summer Arts Festival and related community activities."
                ),
                sponsor_value=(
                    "Provides visible community recognition through alignment "
                    "with accessible arts education."
                ),
                audience_value=(
                    "Supports affordable arts education and meaningful "
                    "learning experiences for local participants."
                ),
                delivery_method=(
                    "Recognition in festival materials and educational "
                    "programming."
                ),
                capacity="Limited",
                exclusivity="Category Exclusive",
                measurement_method=(
                    "Document sponsor recognition delivery and completion of "
                    "all agreed sponsorship benefits."
                ),
                recommended_for_categories=[
                    "financial-institutions",
                ],
            ),
            SponsorshipAssetRecommendation(
                name="Family Activity Sponsor",
                description=(
                    "Support interactive family programming that encourages "
                    "participation throughout the community arts festival."
                ),
                sponsor_value=(
                    "Provides meaningful family engagement while increasing "
                    "visible community brand recognition."
                ),
                audience_value=(
                    "Adds an accessible and interactive experience for "
                    "families and young participants."
                ),
                delivery_method=(
                    "A sponsor-supported family activity area or educational "
                    "experience."
                ),
                capacity="Multiple",
                exclusivity="Non-exclusive",
                measurement_method=(
                    "Track participant engagement, sponsor activation, and "
                    "delivery of all agreed sponsorship benefits."
                ),
                recommended_for_categories=[
                    "healthcare",
                ],
            ),
            SponsorshipAssetRecommendation(
                name="Community Recognition",
                description=(
                    "Recognize sponsors whose support expands community access "
                    "to arts education and cultural programming."
                ),
                sponsor_value=(
                    "Creates strong community goodwill and positive brand "
                    "association through visible local investment."
                ),
                audience_value=(
                    "Helps preserve affordable participation and broader "
                    "community access to festival programming."
                ),
                delivery_method=(
                    "Recognition in event materials, impact communications, "
                    "and post-event reporting."
                ),
                capacity="Multiple",
                exclusivity="Non-exclusive",
                measurement_method=(
                    "Document community impact, sponsor recognition, and "
                    "fulfillment of all sponsorship commitments."
                ),
                recommended_for_categories=[
                    "utilities",
                ],
            ),
        ]
    )


@pytest.fixture
def research():
    return ResearchPrioritySet(
        priorities=[
            ResearchPriorityRecommendation(
                category_slug="financial-institutions",
                priority=1,
                ideal_sponsor_profile=(
                    "Regional banks and credit unions with active community "
                    "investment and education programs."
                ),
                research_direction=(
                    "Research institutions with documented sponsorship, "
                    "financial education, and local giving programs."
                ),
                qualification_signals=[
                    "Active local giving program",
                    "Documented education initiatives",
                ],
                verification_requirements=[
                    "Confirm recent sponsorship history",
                    "Verify regional decision-making authority",
                ],
                disqualification_signals=[
                    "No relevant community investment activity",
                    "No presence in the initiative service area",
                ],
                recommended_asset_names=[
                    "Education Partner",
                ],
                outreach_angle=(
                    "Connect the institution's community education priorities "
                    "with accessible arts learning and local visibility."
                ),
            ),
            ResearchPriorityRecommendation(
                category_slug="healthcare",
                priority=2,
                ideal_sponsor_profile=(
                    "Regional hospitals and healthcare systems with established "
                    "community benefit and family outreach programs."
                ),
                research_direction=(
                    "Review healthcare community benefit reports, outreach "
                    "programs, and family engagement initiatives."
                ),
                qualification_signals=[
                    "Active community benefit program",
                    "Family-focused outreach initiatives",
                ],
                verification_requirements=[
                    "Verify current community outreach priorities",
                    "Confirm sponsorship eligibility requirements",
                ],
                disqualification_signals=[
                    "No relevant community sponsorship activity",
                    "No alignment with family engagement",
                ],
                recommended_asset_names=[
                    "Family Activity Sponsor",
                ],
                outreach_angle=(
                    "Position the partnership as a family-focused community "
                    "engagement opportunity supporting accessible programming."
                ),
            ),
            ResearchPriorityRecommendation(
                category_slug="utilities",
                priority=3,
                ideal_sponsor_profile=(
                    "Regional utility providers with established community "
                    "investment, education, or charitable foundations."
                ),
                research_direction=(
                    "Review annual reports, foundation priorities, and local "
                    "community investment programs."
                ),
                qualification_signals=[
                    "Established community foundation",
                    "Documented regional giving activity",
                ],
                verification_requirements=[
                    "Verify current community funding priorities",
                    "Confirm service-area eligibility",
                ],
                disqualification_signals=[
                    "No regional service presence",
                    "No active community investment program",
                ],
                recommended_asset_names=[
                    "Community Recognition",
                ],
                outreach_angle=(
                    "Connect the utility's local investment goals with visible "
                    "community access and cultural participation."
                ),
            ),
        ]
    )


def test_prompt_contains_context(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
):
    prompt = build_research_priority_prompt(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        assets,
    )

    assert "Community Arts Center" in prompt
    assert "financial-institutions" in prompt
    assert "Education Partner" in prompt


def test_generate_returns_model(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
    research,
):
    client = FakeClient(parsed=research)

    result = generate_research_priorities(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        assets,
        client=client,
        model="test-model",
    )

    assert isinstance(result, ResearchPrioritySet)
    assert len(result.priorities) == 3
    assert result.priorities[0].category_slug == (
        "financial-institutions"
    )
    assert client.responses.last_kwargs["model"] == "test-model"
    assert (
        client.responses.last_kwargs["text_format"]
        is ResearchPrioritySet
    )


def test_missing_response_raises(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
):
    client = FakeClient(parsed=None)

    with pytest.raises(
        ResearchPriorityGenerationError,
        match="no structured research priorities",
    ):
        generate_research_priorities(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
            assets,
            client=client,
        )


def test_api_failure_raises(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
):
    client = FakeClient(
        error=RuntimeError("Temporary API failure"),
    )

    with pytest.raises(
        ResearchPriorityGenerationError,
        match="request could not be completed",
    ):
        generate_research_priorities(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
            assets,
            client=client,
        )
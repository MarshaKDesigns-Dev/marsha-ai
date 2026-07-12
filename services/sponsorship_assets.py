"""AI-powered sponsorship asset generation.

This service accepts an organization, sponsorship initiative, validated
organization analysis, validated sponsorship strategy, and validated sponsor
categories. It returns a structured set of sponsorship assets.

The service does not write to the database and does not generate pricing.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator

from services.organization_analysis import OrganizationAnalysis
from services.sponsor_categories import SponsorCategorySet
from services.sponsorship_strategy import SponsorshipStrategy


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


class SponsorshipAssetGenerationError(RuntimeError):
    """Raised when sponsorship asset generation cannot be completed."""


class SponsorshipAssetRecommendation(BaseModel):
    """A validated sponsorship asset recommendation."""

    name: str = Field(
        min_length=3,
        max_length=200,
        description="A clear sponsorship asset name.",
    )

    description: str = Field(
        min_length=30,
        description=(
            "A specific explanation of what the sponsor receives "
            "or participates in."
        ),
    )

    sponsor_value: str = Field(
        min_length=30,
        description=(
            "The credible business, visibility, engagement, or alignment "
            "value provided to the sponsor."
        ),
    )

    audience_value: str = Field(
        min_length=20,
        description=(
            "How this asset improves the audience, participant, or "
            "community experience."
        ),
    )

    delivery_method: str = Field(
        min_length=10,
        description=(
            "How the organization will deliver or activate the asset."
        ),
    )

    capacity: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "The number or availability limit, such as 1, Limited, "
            "Multiple, or Custom."
        ),
    )

    exclusivity: str = Field(
        min_length=3,
        max_length=150,
        description=(
            "The exclusivity rule, such as Exclusive, Non-exclusive, "
            "Category exclusive, or Not applicable."
        ),
    )

    measurement_method: str = Field(
        min_length=20,
        description=(
            "A practical method for documenting delivery and sponsor value."
        ),
    )

    recommended_for_categories: list[str] = Field(
        min_length=1,
        description=(
            "Sponsor category slugs for which this asset is especially relevant."
        ),
    )

    @field_validator("recommended_for_categories")
    @classmethod
    def normalize_category_slugs(
        cls,
        values: list[str],
    ) -> list[str]:
        """Normalize category slugs and reject duplicates."""

        cleaned_values = [
            value.strip()
            for value in values
            if value and value.strip()
        ]

        if not cleaned_values:
            raise ValueError(
                "At least one recommended sponsor category is required."
            )

        if len(cleaned_values) != len(set(cleaned_values)):
            raise ValueError(
                "Recommended sponsor category slugs must be unique."
            )

        return cleaned_values


class SponsorshipAssetSet(BaseModel):
    """Validated sponsorship asset generation result."""

    assets: list[SponsorshipAssetRecommendation] = Field(
        min_length=3,
        max_length=15,
        description=(
            "A practical set of distinct sponsorship assets."
        ),
    )

    @field_validator("assets")
    @classmethod
    def validate_unique_names(
        cls,
        assets: list[SponsorshipAssetRecommendation],
    ) -> list[SponsorshipAssetRecommendation]:
        """Reject duplicate asset names."""

        normalized_names = [
            asset.name.strip().lower()
            for asset in assets
        ]

        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError(
                "Sponsorship asset names must be unique."
            )

        return assets


SYSTEM_INSTRUCTIONS = """
You are the Sponsorship Asset Worker for a professional sponsorship management
platform.

Generate a practical set of sponsorship assets using the supplied organization
profile, sponsorship initiative, validated organization analysis, validated
sponsorship strategy, and validated sponsor categories.

Follow these rules:

1. Use only the supplied information.
2. Do not invent audience size, attendance, reach, demographics, revenue,
   media exposure, current sponsors, or measurable outcomes.
3. Assets must describe real deliverables the organization could reasonably
   provide.
4. Every asset must create value for both the sponsor and the audience.
5. Assets may include visibility, content, engagement, education, hospitality,
   access, activation, recognition, community impact, or program participation.
6. Avoid generic asset names when a more organization-specific asset is
   supported by the supplied information.
7. Avoid pageant-specific assumptions unless the organization or initiative
   is actually related to pageantry.
8. Work for nonprofits, associations, chambers, museums, schools, sports
   leagues, community organizations, conferences, and events.
9. Recommend relevant sponsor category slugs for every asset.
10. Use only sponsor category slugs supplied in the prompt.
11. Return between 3 and 15 distinct assets.
12. Do not generate pricing, company names, contacts, or outreach messages.
13. Use realistic capacity and exclusivity rules.
14. Include a practical measurement method for every asset.
"""


def _clean(value: Any) -> str:
    """Convert optional values into safe prompt text."""

    if value is None:
        return ""

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value).strip()


def _format_list(values: list[Any]) -> str:
    """Format values as prompt-ready bullet points."""

    cleaned_values = [
        _clean(value)
        for value in values
        if _clean(value)
    ]

    if not cleaned_values:
        return "None provided"

    return "\n".join(
        f"- {value}"
        for value in cleaned_values
    )


def _format_categories(
    category_set: SponsorCategorySet,
) -> str:
    """Format sponsor categories for the asset prompt."""

    lines = []

    for category in category_set.categories:
        lines.append(
            f"- Slug: {category.slug}\n"
            f"  Category: {category.category}\n"
            f"  Fit: {category.fit}\n"
            f"  Priority: {category.priority}\n"
            f"  Ideal sponsor profile: {category.ideal_sponsor_profile}"
        )

    return "\n".join(lines)


def _format_objectives(
    strategy: SponsorshipStrategy,
) -> str:
    """Format strategy objectives for the asset prompt."""

    if not strategy.objectives:
        return "None provided"

    lines = []

    for objective in strategy.objectives:
        lines.append(
            f"- Objective: {objective.objective}\n"
            f"  Rationale: {objective.rationale}\n"
            f"  Success measure: {objective.success_measure}"
        )

    return "\n".join(lines)


def build_asset_prompt(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
    strategy: SponsorshipStrategy,
    categories: SponsorCategorySet,
) -> str:
    """Build the structured prompt used to generate sponsorship assets."""

    organization_name = _clean(
        getattr(organization, "name", "")
    )

    if not organization_name:
        raise SponsorshipAssetGenerationError(
            "Organization name is required before asset generation."
        )

    initiative_name = _clean(
        getattr(initiative, "name", "")
    )

    if not initiative_name:
        raise SponsorshipAssetGenerationError(
            "Sponsorship initiative name is required before asset generation."
        )

    if not isinstance(analysis, OrganizationAnalysis):
        try:
            analysis = OrganizationAnalysis.model_validate(
                analysis
            )
        except ValidationError as exc:
            raise SponsorshipAssetGenerationError(
                "A valid organization analysis is required before "
                "asset generation."
            ) from exc

    if not isinstance(strategy, SponsorshipStrategy):
        try:
            strategy = SponsorshipStrategy.model_validate(
                strategy
            )
        except ValidationError as exc:
            raise SponsorshipAssetGenerationError(
                "A valid sponsorship strategy is required before "
                "asset generation."
            ) from exc

    if not isinstance(categories, SponsorCategorySet):
        try:
            categories = SponsorCategorySet.model_validate(
                categories
            )
        except ValidationError as exc:
            raise SponsorshipAssetGenerationError(
                "A valid sponsor category set is required before "
                "asset generation."
            ) from exc

    return f"""
Generate sponsorship assets for the organization and initiative below.

ORGANIZATION

Name:
{organization_name}

Organization type:
{_clean(getattr(organization, "organization_type", "")) or "Not provided"}

Location:
{_clean(getattr(organization, "location", "")) or "Not provided"}

Mission:
{_clean(getattr(organization, "mission", "")) or "Not provided"}


SPONSORSHIP INITIATIVE

Name:
{initiative_name}

Fundraising target:
{_clean(getattr(initiative, "fundraising_target", "")) or "Not provided"}

Deadline:
{_clean(getattr(initiative, "deadline", "")) or "Not provided"}

Audience:
{_clean(getattr(initiative, "audience", "")) or "Not provided"}

Needs:
{_clean(getattr(initiative, "needs", "")) or "Not provided"}

Goals:
{_clean(getattr(initiative, "goals", "")) or "Not provided"}


VALIDATED ORGANIZATION ANALYSIS

Organization summary:
{analysis.organization_summary}

Initiative summary:
{analysis.initiative_summary}

Mission strengths:
{_format_list(analysis.mission_strengths)}

Community impact:
{_format_list(analysis.community_impact)}

Target audiences:
{_format_list(analysis.target_audiences)}

Sponsor value proposition:
{analysis.sponsor_value_proposition}

Strategy direction:
{analysis.strategy_direction}

Risks or information gaps:
{_format_list(analysis.risks_or_gaps)}


VALIDATED SPONSORSHIP STRATEGY

Positioning statement:
{strategy.positioning_statement}

Strategic theme:
{strategy.strategic_theme}

Recommended approach:
{strategy.recommended_approach}

Objectives:
{_format_objectives(strategy)}

Sponsor benefits:
{_format_list(strategy.sponsor_benefits)}

Partnership principles:
{_format_list(strategy.partnership_principles)}

Activation priorities:
{_format_list(strategy.activation_priorities)}

Measurement priorities:
{_format_list(strategy.measurement_priorities)}

Risks or constraints:
{_format_list(strategy.risks_or_constraints)}


VALIDATED SPONSOR CATEGORIES

{_format_categories(categories)}


Generate between 3 and 15 distinct sponsorship assets.

Every asset must include:

- a specific asset name
- a clear description
- sponsor value
- audience value
- delivery method
- realistic capacity
- an exclusivity rule
- a measurement method
- one or more recommended sponsor category slugs

Use only the category slugs supplied above.

Do not generate pricing, company names, contacts, or outreach copy.
""".strip()


def generate_sponsorship_assets(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
    strategy: SponsorshipStrategy,
    categories: SponsorCategorySet,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> SponsorshipAssetSet:
    """Generate validated sponsorship assets."""

    prompt = build_asset_prompt(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
    )

    openai_client = client or OpenAI()
    selected_model = model or DEFAULT_MODEL

    try:
        response = openai_client.responses.parse(
            model=selected_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            text_format=SponsorshipAssetSet,
        )
    except Exception as exc:
        raise SponsorshipAssetGenerationError(
            "The sponsorship asset request could not be completed."
        ) from exc

    parsed_result = getattr(
        response,
        "output_parsed",
        None,
    )

    if parsed_result is None:
        raise SponsorshipAssetGenerationError(
            "OpenAI returned no structured sponsorship assets."
        )

    if isinstance(parsed_result, SponsorshipAssetSet):
        return parsed_result

    try:
        return SponsorshipAssetSet.model_validate(
            parsed_result
        )
    except ValidationError as exc:
        raise SponsorshipAssetGenerationError(
            "OpenAI returned invalid sponsorship assets."
        ) from exc
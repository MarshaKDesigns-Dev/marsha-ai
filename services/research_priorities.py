"""AI-powered sponsor research priority generation.

This service accepts an organization, sponsorship initiative, validated
organization analysis, validated sponsorship strategy, validated sponsor
categories, and validated sponsorship assets. It returns a structured research
priority plan.

The service does not write to the database and does not research companies.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator

from services.organization_analysis import OrganizationAnalysis
from services.sponsor_categories import SponsorCategorySet
from services.sponsorship_assets import SponsorshipAssetSet
from services.sponsorship_strategy import SponsorshipStrategy


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


class ResearchPriorityGenerationError(RuntimeError):
    """Raised when research priority generation cannot be completed."""


class ResearchPriorityRecommendation(BaseModel):
    """A validated research priority recommendation."""

    category_slug: str = Field(
        min_length=2,
        max_length=100,
        description="A sponsor category slug from the validated category set.",
    )

    priority: int = Field(
        ge=1,
        description="Research priority where 1 is the highest priority.",
    )

    ideal_sponsor_profile: str = Field(
        min_length=20,
        description=(
            "A practical description of the type of company or institution "
            "that should be researched first."
        ),
    )

    research_direction: str = Field(
        min_length=30,
        description=(
            "Specific guidance for identifying and evaluating prospects."
        ),
    )

    qualification_signals: list[str] = Field(
        min_length=1,
        description=(
            "Evidence that would indicate a prospect is a strong fit."
        ),
    )

    verification_requirements: list[str] = Field(
        min_length=1,
        description=(
            "Facts or sources that should be verified before approval."
        ),
    )

    disqualification_signals: list[str] = Field(
        min_length=1,
        description=(
            "Evidence that should reduce priority or disqualify the prospect."
        ),
    )

    recommended_asset_names: list[str] = Field(
        min_length=1,
        description=(
            "Names of validated sponsorship assets likely to fit this category."
        ),
    )

    outreach_angle: str = Field(
        min_length=30,
        description=(
            "A research-informed partnership angle for future outreach."
        ),
    )

    @field_validator(
        "qualification_signals",
        "verification_requirements",
        "disqualification_signals",
        "recommended_asset_names",
    )
    @classmethod
    def reject_duplicates(cls, values: list[str]) -> list[str]:
        """Normalize list values and reject duplicates."""

        cleaned_values = [
            value.strip()
            for value in values
            if value and value.strip()
        ]

        if not cleaned_values:
            raise ValueError("At least one value is required.")

        normalized = [
            value.lower()
            for value in cleaned_values
        ]

        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate values are not allowed.")

        return cleaned_values


class ResearchPrioritySet(BaseModel):
    """Validated research priority generation result."""

    priorities: list[ResearchPriorityRecommendation] = Field(
        min_length=1,
        description=(
            "A prioritized research plan covering the validated categories."
        ),
    )

    @field_validator("priorities")
    @classmethod
    def validate_priorities(
        cls,
        priorities: list[ResearchPriorityRecommendation],
    ) -> list[ResearchPriorityRecommendation]:
        """Reject duplicate category slugs and invalid priority sequences."""

        category_slugs = [
            item.category_slug
            for item in priorities
        ]

        priority_values = [
            item.priority
            for item in priorities
        ]

        if len(category_slugs) != len(set(category_slugs)):
            raise ValueError(
                "Research priority category slugs must be unique."
            )

        if len(priority_values) != len(set(priority_values)):
            raise ValueError(
                "Research priority values must be unique."
            )

        expected_priorities = list(
            range(1, len(priorities) + 1)
        )

        if sorted(priority_values) != expected_priorities:
            raise ValueError(
                "Research priorities must be consecutive starting at 1."
            )

        return sorted(
            priorities,
            key=lambda item: item.priority,
        )


SYSTEM_INSTRUCTIONS = """
You are the Research Priority Worker for a professional sponsorship management
platform.

Create a practical research plan using the supplied organization profile,
sponsorship initiative, validated organization analysis, validated sponsorship
strategy, validated sponsor categories, and validated sponsorship assets.

Follow these rules:

1. Use only the supplied information.
2. Do not invent company names, contacts, audience size, attendance, revenue,
   demographics, current sponsors, media exposure, or measurable results.
3. Create one research priority for each supplied sponsor category.
4. Use only category slugs supplied in the prompt.
5. Use only sponsorship asset names supplied in the prompt.
6. Assign unique consecutive priorities beginning with 1.
7. Identify practical qualification signals.
8. Identify facts that must be verified before a prospect is approved.
9. Identify realistic disqualification signals.
10. Provide a research direction specific to the category and initiative.
11. Provide a credible future outreach angle without writing outreach copy.
12. Distinguish sponsorship fit from general charitable giving.
13. Avoid pageant-specific assumptions unless the organization or initiative
    is actually related to pageantry.
14. Work for nonprofits, associations, chambers, museums, schools, sports
    leagues, community organizations, conferences, and events.
15. Do not generate company names, contacts, email addresses, pricing,
    proposals, or outreach messages.
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
    categories: SponsorCategorySet,
) -> str:
    """Format sponsor categories for the research prompt."""

    lines = []

    for category in categories.categories:
        lines.append(
            f"- Slug: {category.slug}\n"
            f"  Category: {category.category}\n"
            f"  Fit: {category.fit}\n"
            f"  Score: {category.score}\n"
            f"  Priority: {category.priority}\n"
            f"  Ideal sponsor profile: {category.ideal_sponsor_profile}\n"
            f"  Research direction: {category.research_direction}"
        )

    return "\n".join(lines)


def _format_assets(
    assets: SponsorshipAssetSet,
) -> str:
    """Format sponsorship assets for the research prompt."""

    lines = []

    for asset in assets.assets:
        lines.append(
            f"- Name: {asset.name}\n"
            f"  Description: {asset.description}\n"
            f"  Sponsor value: {asset.sponsor_value}\n"
            f"  Capacity: {asset.capacity}\n"
            f"  Exclusivity: {asset.exclusivity}\n"
            f"  Recommended category slugs: "
            f"{', '.join(asset.recommended_for_categories)}"
        )

    return "\n".join(lines)


def _format_objectives(
    strategy: SponsorshipStrategy,
) -> str:
    """Format sponsorship objectives for the research prompt."""

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


def build_research_priority_prompt(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
    strategy: SponsorshipStrategy,
    categories: SponsorCategorySet,
    assets: SponsorshipAssetSet,
) -> str:
    """Build the structured prompt used to generate research priorities."""

    organization_name = _clean(
        getattr(organization, "name", "")
    )

    if not organization_name:
        raise ResearchPriorityGenerationError(
            "Organization name is required before research priority generation."
        )

    initiative_name = _clean(
        getattr(initiative, "name", "")
    )

    if not initiative_name:
        raise ResearchPriorityGenerationError(
            "Sponsorship initiative name is required before "
            "research priority generation."
        )

    if not isinstance(analysis, OrganizationAnalysis):
        try:
            analysis = OrganizationAnalysis.model_validate(
                analysis
            )
        except ValidationError as exc:
            raise ResearchPriorityGenerationError(
                "A valid organization analysis is required before "
                "research priority generation."
            ) from exc

    if not isinstance(strategy, SponsorshipStrategy):
        try:
            strategy = SponsorshipStrategy.model_validate(
                strategy
            )
        except ValidationError as exc:
            raise ResearchPriorityGenerationError(
                "A valid sponsorship strategy is required before "
                "research priority generation."
            ) from exc

    if not isinstance(categories, SponsorCategorySet):
        try:
            categories = SponsorCategorySet.model_validate(
                categories
            )
        except ValidationError as exc:
            raise ResearchPriorityGenerationError(
                "A valid sponsor category set is required before "
                "research priority generation."
            ) from exc

    if not isinstance(assets, SponsorshipAssetSet):
        try:
            assets = SponsorshipAssetSet.model_validate(
                assets
            )
        except ValidationError as exc:
            raise ResearchPriorityGenerationError(
                "A valid sponsorship asset set is required before "
                "research priority generation."
            ) from exc

    return f"""
Create a sponsor research priority plan for the organization and initiative
below.

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


VALIDATED SPONSORSHIP ASSETS

{_format_assets(assets)}


Create exactly one research priority for each supplied sponsor category.

Every research priority must include:

- the supplied category slug
- a unique consecutive priority beginning with 1
- an ideal sponsor profile
- a category-specific research direction
- qualification signals
- verification requirements
- disqualification signals
- one or more supplied sponsorship asset names
- a future outreach angle

Use only the category slugs and sponsorship asset names supplied above.

Do not generate company names, contacts, email addresses, pricing, proposals,
or outreach copy.
""".strip()


def _validate_cross_references(
    result: ResearchPrioritySet,
    categories: SponsorCategorySet,
    assets: SponsorshipAssetSet,
) -> None:
    """Ensure generated references exist in the validated inputs."""

    allowed_category_slugs = {
        category.slug
        for category in categories.categories
    }

    allowed_asset_names = {
        asset.name
        for asset in assets.assets
    }

    result_category_slugs = {
        item.category_slug
        for item in result.priorities
    }

    if result_category_slugs != allowed_category_slugs:
        raise ResearchPriorityGenerationError(
            "Research priorities must cover every sponsor category exactly once."
        )

    for item in result.priorities:
        invalid_asset_names = set(
            item.recommended_asset_names
        ) - allowed_asset_names

        if invalid_asset_names:
            raise ResearchPriorityGenerationError(
                "Research priorities referenced unknown sponsorship assets."
            )


def generate_research_priorities(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
    strategy: SponsorshipStrategy,
    categories: SponsorCategorySet,
    assets: SponsorshipAssetSet,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> ResearchPrioritySet:
    """Generate validated sponsor research priorities."""

    prompt = build_research_priority_prompt(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        assets,
    )

    openai_client = client or OpenAI()
    selected_model = model or DEFAULT_MODEL

    try:
        response = openai_client.responses.parse(
            model=selected_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            text_format=ResearchPrioritySet,
        )
    except Exception as exc:
        raise ResearchPriorityGenerationError(
            "The research priority request could not be completed."
        ) from exc

    parsed_result = getattr(
        response,
        "output_parsed",
        None,
    )

    if parsed_result is None:
        raise ResearchPriorityGenerationError(
            "OpenAI returned no structured research priorities."
        )

    if isinstance(parsed_result, ResearchPrioritySet):
        result = parsed_result
    else:
        try:
            result = ResearchPrioritySet.model_validate(
                parsed_result
            )
        except ValidationError as exc:
            raise ResearchPriorityGenerationError(
                "OpenAI returned invalid research priorities."
            ) from exc

    _validate_cross_references(
        result,
        categories,
        assets,
    )

    return result
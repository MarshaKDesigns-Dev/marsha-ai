"""AI-powered sponsor category generation.

This service accepts an organization, sponsorship initiative, validated
organization analysis, and validated sponsorship strategy. It returns a
structured list of sponsor categories.

The service does not write to the database and does not generate company names.
"""

from __future__ import annotations

import os
import re
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator

from services.organization_analysis import OrganizationAnalysis
from services.sponsorship_strategy import SponsorshipStrategy


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


class SponsorCategoryGenerationError(RuntimeError):
    """Raised when sponsor category generation cannot be completed."""


class SponsorCategoryRecommendation(BaseModel):
    """A validated sponsor category recommendation."""

    slug: str = Field(
        min_length=2,
        max_length=100,
        description=(
            "A lowercase URL-safe identifier using letters, numbers, "
            "and hyphens only."
        ),
    )

    category: str = Field(
        min_length=3,
        max_length=200,
        description="The sponsor category name.",
    )

    fit: str = Field(
        min_length=30,
        description=(
            "A specific explanation of why this category aligns with the "
            "organization, initiative, audience, and strategy."
        ),
    )

    score: int = Field(
        ge=0,
        le=100,
        description="Strategic fit score from 0 to 100.",
    )

    priority: int = Field(
        ge=1,
        description=(
            "Research priority where 1 is the highest-priority category."
        ),
    )

    ideal_sponsor_profile: str = Field(
        min_length=20,
        description=(
            "A practical description of the type of organization that would "
            "be a strong fit within this category."
        ),
    )

    research_direction: str = Field(
        min_length=20,
        description=(
            "Specific guidance for researching prospects in this category."
        ),
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        """Ensure slugs are lowercase and URL safe."""

        cleaned_value = value.strip()

        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cleaned_value):
            raise ValueError(
                "Slug must contain lowercase letters, numbers, "
                "and single hyphens only."
            )

        return cleaned_value


class SponsorCategorySet(BaseModel):
    """Validated sponsor category generation result."""

    categories: list[SponsorCategoryRecommendation] = Field(
        min_length=3,
        max_length=10,
        description=(
            "A prioritized set of distinct sponsor categories."
        ),
    )

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        categories: list[SponsorCategoryRecommendation],
    ) -> list[SponsorCategoryRecommendation]:
        """Reject duplicate slugs and duplicate priorities."""

        slugs = [category.slug for category in categories]
        priorities = [category.priority for category in categories]

        if len(slugs) != len(set(slugs)):
            raise ValueError("Sponsor category slugs must be unique.")

        if len(priorities) != len(set(priorities)):
            raise ValueError("Sponsor category priorities must be unique.")

        expected_priorities = list(
            range(1, len(categories) + 1)
        )

        if sorted(priorities) != expected_priorities:
            raise ValueError(
                "Sponsor category priorities must be consecutive "
                "starting at 1."
            )

        return sorted(
            categories,
            key=lambda category: category.priority,
        )


SYSTEM_INSTRUCTIONS = """
You are the Sponsor Category Worker for a professional sponsorship management
platform.

Generate a prioritized set of sponsor categories using the supplied
organization profile, sponsorship initiative, validated organization analysis,
and validated sponsorship strategy.

Follow these rules:

1. Use only the supplied information.
2. Generate business categories, not company names.
3. Do not invent audience size, attendance, demographics, reach, revenue,
   media exposure, current sponsors, or measurable outcomes.
4. Every category must have a specific strategic rationale.
5. Categories must reflect sponsor business value, audience relevance,
   community alignment, activation potential, and initiative needs.
6. Avoid generic categories unless the supplied information supports them.
7. Avoid pageant-specific assumptions unless the organization or initiative
   is actually related to pageantry.
8. Work for nonprofits, associations, chambers, museums, schools, sports
   leagues, community organizations, conferences, and events.
9. Use unique lowercase URL-safe slugs.
10. Assign unique consecutive priorities beginning with 1.
11. Return between 3 and 10 categories.
12. Do not generate sponsorship assets, pricing, company names, contacts,
    or outreach messages.
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


def _format_objectives(
    strategy: SponsorshipStrategy,
) -> str:
    """Format strategy objectives for the category prompt."""

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


def build_category_prompt(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
    strategy: SponsorshipStrategy,
) -> str:
    """Build the structured prompt used to generate sponsor categories."""

    organization_name = _clean(
        getattr(organization, "name", "")
    )

    if not organization_name:
        raise SponsorCategoryGenerationError(
            "Organization name is required before category generation."
        )

    initiative_name = _clean(
        getattr(initiative, "name", "")
    )

    if not initiative_name:
        raise SponsorCategoryGenerationError(
            "Sponsorship initiative name is required before "
            "category generation."
        )

    if not isinstance(analysis, OrganizationAnalysis):
        try:
            analysis = OrganizationAnalysis.model_validate(
                analysis
            )
        except ValidationError as exc:
            raise SponsorCategoryGenerationError(
                "A valid organization analysis is required before "
                "category generation."
            ) from exc

    if not isinstance(strategy, SponsorshipStrategy):
        try:
            strategy = SponsorshipStrategy.model_validate(
                strategy
            )
        except ValidationError as exc:
            raise SponsorCategoryGenerationError(
                "A valid sponsorship strategy is required before "
                "category generation."
            ) from exc

    return f"""
Generate sponsor categories for the organization and initiative below.

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


Generate between 3 and 10 distinct sponsor categories.

Each category must include:

- a unique lowercase URL-safe slug
- a clear category name
- a specific fit explanation
- a score from 0 to 100
- a unique consecutive priority beginning with 1
- an ideal sponsor profile
- a research direction

Do not generate company names, contacts, assets, pricing, or outreach copy.
""".strip()


def generate_sponsor_categories(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
    strategy: SponsorshipStrategy,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> SponsorCategorySet:
    """Generate validated sponsor categories.

    Args:
        organization:
            An Organization model instance or compatible object.

        initiative:
            A SponsorshipInitiative model instance or compatible object.

        analysis:
            A validated OrganizationAnalysis result.

        strategy:
            A validated SponsorshipStrategy result.

        client:
            Optional OpenAI client for testing or dependency injection.

        model:
            Optional OpenAI model override.

    Returns:
        A validated SponsorCategorySet instance.

    Raises:
        SponsorCategoryGenerationError:
            If required information is missing, the API request fails, or the
            response cannot be validated.
    """

    prompt = build_category_prompt(
        organization,
        initiative,
        analysis,
        strategy,
    )

    openai_client = client or OpenAI()
    selected_model = model or DEFAULT_MODEL

    try:
        response = openai_client.responses.parse(
            model=selected_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            text_format=SponsorCategorySet,
        )
    except Exception as exc:
        raise SponsorCategoryGenerationError(
            "The sponsor category request could not be completed."
        ) from exc

    parsed_result = getattr(
        response,
        "output_parsed",
        None,
    )

    if parsed_result is None:
        raise SponsorCategoryGenerationError(
            "OpenAI returned no structured sponsor categories."
        )

    if isinstance(parsed_result, SponsorCategorySet):
        return parsed_result

    try:
        return SponsorCategorySet.model_validate(
            parsed_result
        )
    except ValidationError as exc:
        raise SponsorCategoryGenerationError(
            "OpenAI returned invalid sponsor categories."
        ) from exc
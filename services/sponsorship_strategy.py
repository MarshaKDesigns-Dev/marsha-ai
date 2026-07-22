"""AI-powered sponsorship strategy generation.

This service accepts an organization, sponsorship initiative, and validated
organization analysis. It returns a structured sponsorship strategy.

The service does not write to the database.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from services.organization_analysis import OrganizationAnalysis
from services.openai_generation_timeout import (
    GenerationStepTimeoutError,
    OPENAI_REQUEST_TIMEOUT_SECONDS,
    parse_with_timeout,
)


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


class SponsorshipStrategyError(RuntimeError):
    """Raised when sponsorship strategy generation cannot be completed."""


class SponsorshipObjective(BaseModel):
    """A specific objective for the sponsorship initiative."""

    objective: str = Field(
        min_length=10,
        description="A concrete sponsorship objective.",
    )

    rationale: str = Field(
        min_length=20,
        description=(
            "Why this objective matters to the organization and initiative."
        ),
    )

    success_measure: str = Field(
        min_length=10,
        description=(
            "A practical way the organization could determine whether "
            "the objective was achieved."
        ),
    )


class SponsorshipStrategy(BaseModel):
    """Validated sponsorship strategy returned by the AI worker."""

    positioning_statement: str = Field(
        min_length=30,
        description=(
            "A concise statement describing how the initiative should be "
            "positioned to prospective sponsors."
        ),
    )

    strategic_theme: str = Field(
        min_length=10,
        description=(
            "The central strategic idea that should unify sponsorship efforts."
        ),
    )

    recommended_approach: str = Field(
        min_length=40,
        description=(
            "A practical explanation of how the organization should approach "
            "sponsorship development."
        ),
    )

    objectives: list[SponsorshipObjective] = Field(
        min_length=1,
        description=(
            "Specific sponsorship objectives with rationales and "
            "success measures."
        ),
    )

    sponsor_benefits: list[str] = Field(
        min_length=1,
        description=(
            "Credible benefits that sponsors may receive through the initiative."
        ),
    )

    partnership_principles: list[str] = Field(
        min_length=1,
        description=(
            "Rules that should guide sponsor selection and partnership design."
        ),
    )

    activation_priorities: list[str] = Field(
        min_length=1,
        description=(
            "Priority ways sponsors could participate, engage, or receive value."
        ),
    )

    measurement_priorities: list[str] = Field(
        min_length=1,
        description=(
            "The results and evidence the organization should track."
        ),
    )

    recommended_next_steps: list[str] = Field(
        min_length=1,
        description=(
            "Ordered actions the organization should take after strategy "
            "generation."
        ),
    )

    risks_or_constraints: list[str] = Field(
        default_factory=list,
        description=(
            "Known limitations, missing information, or constraints that could "
            "affect execution."
        ),
    )


SYSTEM_INSTRUCTIONS = """
You are the Sponsorship Strategy Worker for a professional sponsorship
management platform.

Create a practical sponsorship strategy using the supplied organization
profile, initiative information, and validated organization analysis.

Your work will later be used to generate sponsor categories, sponsorship
assets, research priorities, prospect recommendations, and outreach.

Follow these rules:

1. Use only the supplied information.
2. Do not invent audience size, attendance, demographics, revenue, media
   exposure, partnerships, sponsors, reach, or measurable results.
3. Do not treat sponsorship as a charitable donation.
4. Explain the business value that a suitable sponsor could receive.
5. Recommend objectives and measures that are realistic for the available
   information.
6. Place missing information or weaknesses in risks_or_constraints.
7. Make the strategy specific to the organization and initiative.
8. Avoid pageant-specific assumptions unless the organization or initiative
   is actually related to pageantry.
9. Work for nonprofits, associations, chambers, museums, schools, sports
   leagues, community organizations, conferences, and events.
10. Do not generate sponsor company names, sponsor categories, sponsorship
    assets, pricing, or outreach messages in this response.
"""


def _clean(value: Any) -> str:
    """Convert optional values into safe prompt text."""

    if value is None:
        return ""

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value).strip()


def _format_list(values: list[str]) -> str:
    """Format a list for inclusion in the AI prompt."""

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


def build_strategy_prompt(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
) -> str:
    """Build the structured prompt used to generate a strategy."""

    organization_name = _clean(
        getattr(organization, "name", "")
    )

    if not organization_name:
        raise SponsorshipStrategyError(
            "Organization name is required before strategy generation."
        )

    initiative_name = _clean(
        getattr(initiative, "name", "")
    )

    if not initiative_name:
        raise SponsorshipStrategyError(
            "Sponsorship initiative name is required before "
            "strategy generation."
        )

    if not isinstance(analysis, OrganizationAnalysis):
        try:
            analysis = OrganizationAnalysis.model_validate(analysis)
        except ValidationError as exc:
            raise SponsorshipStrategyError(
                "A valid organization analysis is required before "
                "strategy generation."
            ) from exc

    return f"""
Develop a sponsorship strategy for the organization and initiative below.

ORGANIZATION

Name:
{organization_name}

Organization type:
{_clean(getattr(organization, "organization_type", "")) or "Not provided"}

Location:
{_clean(getattr(organization, "location", "")) or "Not provided"}

Mission:
{_clean(getattr(organization, "mission", "")) or "Not provided"}

Website:
{_clean(getattr(organization, "website", "")) or "Not provided"}


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

Sponsorship objectives identified during analysis:
{_format_list(analysis.sponsorship_objectives)}

Sponsor value proposition:
{analysis.sponsor_value_proposition}

Strategy direction:
{analysis.strategy_direction}

Risks or information gaps:
{_format_list(analysis.risks_or_gaps)}


Create a specific, executable sponsorship strategy.

Do not create sponsor categories, company names, sponsorship assets, pricing,
or outreach copy. Those will be generated by later workers.

Do not fabricate facts. Carry unresolved information gaps into
risks_or_constraints.
""".strip()


def generate_sponsorship_strategy(
    organization: Any,
    initiative: Any,
    analysis: OrganizationAnalysis,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    request_timeout: float = OPENAI_REQUEST_TIMEOUT_SECONDS,
    workflow_started_at: float | None = None,
) -> SponsorshipStrategy:
    """Generate a validated sponsorship strategy.

    Args:
        organization:
            An Organization model instance or compatible object.

        initiative:
            A SponsorshipInitiative model instance or compatible object.

        analysis:
            A validated OrganizationAnalysis result.

        client:
            Optional OpenAI client for testing or dependency injection.

        model:
            Optional OpenAI model override.

    Returns:
        A validated SponsorshipStrategy instance.

    Raises:
        SponsorshipStrategyError:
            If required information is missing, the API request fails, or the
            response cannot be validated.
    """

    prompt = build_strategy_prompt(
        organization,
        initiative,
        analysis,
    )

    openai_client = client or OpenAI()
    selected_model = model or DEFAULT_MODEL

    try:
        response = parse_with_timeout(
            client=openai_client,
            generation_step="sponsorship_strategy",
            organization=organization,
            initiative=initiative,
            request_timeout=request_timeout,
            workflow_started_at=workflow_started_at,
            model=selected_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            text_format=SponsorshipStrategy,
        )
    except GenerationStepTimeoutError:
        raise
    except Exception as exc:
        raise SponsorshipStrategyError(
            "The sponsorship strategy request could not be completed."
        ) from exc

    parsed_result = getattr(
        response,
        "output_parsed",
        None,
    )

    if parsed_result is None:
        raise SponsorshipStrategyError(
            "OpenAI returned no structured sponsorship strategy."
        )

    if isinstance(parsed_result, SponsorshipStrategy):
        return parsed_result

    try:
        return SponsorshipStrategy.model_validate(
            parsed_result
        )
    except ValidationError as exc:
        raise SponsorshipStrategyError(
            "OpenAI returned an invalid sponsorship strategy."
        ) from exc

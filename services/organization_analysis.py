"""AI-powered organization and sponsorship initiative analysis.

This service accepts existing Organization and SponsorshipInitiative model
instances, sends their structured information to OpenAI, and returns a
validated OrganizationAnalysis object.

The service does not write to the database.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from services.openai_generation_timeout import (
    GenerationStepTimeoutError,
    OPENAI_REQUEST_TIMEOUT_SECONDS,
    parse_with_timeout,
)


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


class OrganizationAnalysisError(RuntimeError):
    """Raised when organization analysis cannot be completed."""


class OrganizationAnalysis(BaseModel):
    """Validated result returned by the organization analysis worker."""

    organization_summary: str = Field(
        min_length=20,
        description=(
            "A concise explanation of the organization, its mission, "
            "community role, and sponsorship relevance."
        ),
    )

    initiative_summary: str = Field(
        min_length=20,
        description=(
            "A concise explanation of the sponsorship initiative, "
            "its purpose, timeline, audience, and funding needs."
        ),
    )

    mission_strengths: list[str] = Field(
        min_length=1,
        description=(
            "Specific organizational strengths that can create sponsor value."
        ),
    )

    community_impact: list[str] = Field(
        min_length=1,
        description=(
            "The primary ways the organization or initiative affects "
            "its community or audience."
        ),
    )

    target_audiences: list[str] = Field(
        min_length=1,
        description=(
            "Distinct audiences that sponsors could reach through "
            "the organization or initiative."
        ),
    )

    sponsorship_objectives: list[str] = Field(
        min_length=1,
        description=(
            "Concrete outcomes the organization should pursue through "
            "sponsorship."
        ),
    )

    sponsor_value_proposition: str = Field(
        min_length=20,
        description=(
            "A clear explanation of why a sponsor would benefit from "
            "supporting this initiative."
        ),
    )

    strategy_direction: str = Field(
        min_length=20,
        description=(
            "The recommended strategic direction for building the "
            "sponsorship program."
        ),
    )

    risks_or_gaps: list[str] = Field(
        default_factory=list,
        description=(
            "Missing information, weaknesses, or risks that may reduce "
            "sponsorship readiness."
        ),
    )


SYSTEM_INSTRUCTIONS = """
You are the Organization Analysis Worker for a professional sponsorship
management platform.

Analyze the organization and its sponsorship initiative as a sponsorship
strategist. Your analysis will be used by later AI workers to generate sponsor
categories, sponsorship assets, prospect research priorities, and outreach.

Your analysis must:

1. Use only the information provided.
2. Never invent attendance, demographics, reach, revenue, partnerships,
   sponsors, media exposure, or measurable results.
3. Clearly identify missing information as a risk or gap.
4. Focus on sponsor value, audience access, community impact, brand alignment,
   visibility, engagement, and measurable business outcomes.
5. Work for any nonprofit, association, chamber, sports league, museum,
   school, community organization, or event.
6. Avoid pageant-specific assumptions unless the supplied organization or
   initiative is actually a pageant.
7. Return concrete, organization-specific analysis rather than generic
   fundraising advice.
8. Distinguish charitable donations from strategic sponsorship.
"""


def _clean(value: Any) -> str:
    """Convert optional model values into safe prompt text."""

    if value is None:
        return ""

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value).strip()


def build_analysis_prompt(
    organization: Any,
    initiative: Any,
) -> str:
    """Build the structured input sent to the AI worker."""

    organization_name = _clean(getattr(organization, "name", ""))

    if not organization_name:
        raise OrganizationAnalysisError(
            "Organization name is required before AI analysis."
        )

    initiative_name = _clean(getattr(initiative, "name", ""))

    if not initiative_name:
        raise OrganizationAnalysisError(
            "Sponsorship initiative name is required before AI analysis."
        )

    return f"""
Analyze the following organization and sponsorship initiative.

ORGANIZATION PROFILE

Organization name:
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

Initiative name:
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


Produce an evidence-based sponsorship analysis that later workers can use to
create the sponsorship strategy, sponsor categories, sponsorship assets, and
research priorities.

Do not fabricate facts. Place missing or weak information in risks_or_gaps.
""".strip()


def analyze_organization(
    organization: Any,
    initiative: Any,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    request_timeout: float = OPENAI_REQUEST_TIMEOUT_SECONDS,
    workflow_started_at: float | None = None,
) -> OrganizationAnalysis:
    """Analyze an organization and initiative using structured AI output.

    Args:
        organization:
            An Organization model instance or compatible object.

        initiative:
            A SponsorshipInitiative model instance or compatible object.

        client:
            Optional OpenAI client. Supplying a client allows tests to use
            a mock without making an external API request.

        model:
            Optional OpenAI model override.

    Returns:
        A validated OrganizationAnalysis instance.

    Raises:
        OrganizationAnalysisError:
            If required data is missing, the API request fails, or the
            response cannot be validated.
    """

    prompt = build_analysis_prompt(organization, initiative)
    openai_client = client or OpenAI()
    selected_model = model or DEFAULT_MODEL

    try:
        response = parse_with_timeout(
            client=openai_client,
            generation_step="organization_analysis",
            organization=organization,
            initiative=initiative,
            request_timeout=request_timeout,
            workflow_started_at=workflow_started_at,
            model=selected_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            text_format=OrganizationAnalysis,
        )
    except GenerationStepTimeoutError:
        raise
    except Exception as exc:
        raise OrganizationAnalysisError(
            "The organization analysis request could not be completed."
        ) from exc

    parsed_result = getattr(response, "output_parsed", None)

    if parsed_result is None:
        raise OrganizationAnalysisError(
            "OpenAI returned no structured organization analysis."
        )

    if isinstance(parsed_result, OrganizationAnalysis):
        return parsed_result

    try:
        return OrganizationAnalysis.model_validate(parsed_result)
    except ValidationError as exc:
        raise OrganizationAnalysisError(
            "OpenAI returned an invalid organization analysis."
        ) from exc

from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from services.openai_generation_timeout import GenerationStepTimeoutError
from services.organization_analysis import (
    OrganizationAnalysis,
    OrganizationAnalysisError,
    analyze_organization,
    build_analysis_prompt,
)


class FakeResponse:
    def __init__(self, parsed):
        self.output_parsed = parsed


class FakeResponsesAPI:
    def __init__(self, parsed, error=None):
        self._parsed = parsed
        self._error = error

    def parse(self, **kwargs):
        if self._error:
            raise self._error
        return FakeResponse(self._parsed)


class FakeClient:
    def __init__(self, parsed=None, error=None):
        self.responses = FakeResponsesAPI(parsed, error)
        self.last_options = None

    def with_options(self, **kwargs):
        self.last_options = kwargs
        return self


@pytest.fixture
def organization():
    return SimpleNamespace(
        name="Community Arts Center",
        organization_type="Nonprofit",
        location="Durham, NC",
        mission="Providing affordable arts education.",
        website="https://example.org",
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


def test_build_prompt_contains_organization_name(organization, initiative):
    prompt = build_analysis_prompt(organization, initiative)

    assert "Community Arts Center" in prompt
    assert "Summer Arts Festival" in prompt


def test_missing_organization_name_raises(initiative):
    org = SimpleNamespace(name="")

    with pytest.raises(OrganizationAnalysisError):
        build_analysis_prompt(org, initiative)


def test_missing_initiative_name_raises(organization):
    init = SimpleNamespace(name="")

    with pytest.raises(OrganizationAnalysisError):
        build_analysis_prompt(organization, init)


def test_analysis_returns_valid_model(organization, initiative):
    parsed = OrganizationAnalysis(
        organization_summary=(
            "Community arts nonprofit serving local residents through "
            "education and events."
        ),
        initiative_summary=(
            "Annual summer arts festival designed to increase "
            "participation and fundraising."
        ),
        mission_strengths=[
            "Community engagement"
        ],
        community_impact=[
            "Arts education"
        ],
        target_audiences=[
            "Families"
        ],
        sponsorship_objectives=[
            "Increase sponsorship revenue"
        ],
        sponsor_value_proposition=(
            "Sponsors receive strong community visibility."
        ),
        strategy_direction=(
            "Focus on regional businesses with community investment goals."
        ),
        risks_or_gaps=[],
    )

    client = FakeClient(parsed)

    result = analyze_organization(
        organization,
        initiative,
        client=client,
    )

    assert isinstance(result, OrganizationAnalysis)
    assert result.organization_summary.startswith("Community")
    assert result.target_audiences == ["Families"]
    assert client.last_options == {"timeout": 45.0, "max_retries": 0}


def test_invalid_response_raises(organization, initiative):
    client = FakeClient(None)

    with pytest.raises(OrganizationAnalysisError):
        analyze_organization(
            organization,
            initiative,
            client=client,
        )


def test_analysis_timeout_preserves_generation_step(
    organization,
    initiative,
):
    timeout = APITimeoutError(request=httpx.Request("POST", "https://api"))

    with pytest.raises(GenerationStepTimeoutError) as exc_info:
        analyze_organization(
            organization,
            initiative,
            client=FakeClient(error=timeout),
        )

    assert exc_info.value.generation_step == "organization_analysis"

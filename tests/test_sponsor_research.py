"""Tests for evidence-backed sponsor web research."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import httpx
from openai import APITimeoutError
from pydantic import ValidationError

from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_research import (
    ConfidenceLevel,
    ContributionType,
    EvidenceType,
    NoCredibleProspectsError,
    ProspectEvidence,
    PublicBusinessContact,
    SponsorProspectCandidate,
    SponsorResearchResult,
    SponsorResearchError,
    SponsorResearchUnavailableError,
    VerifiedFact,
    collect_web_search_source_urls,
    research_sponsor_category,
    sponsor_research_max_output_tokens,
    validate_researched_prospects,
)


def eligibility(audience="Adults 21 and older"):
    return SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support community education.",
            location="Durham, NC",
            initiative_name="Education Conference",
            audience=audience,
        )
    )


def raw_response(response, *, status_code=200):
    raw = MagicMock(status_code=status_code)
    raw.parse.return_value = response
    return raw


def provider_response(
    output_text=None,
    *,
    status="completed",
    incomplete_reason=None,
    include_web_search=False,
    refusal=False,
):
    output = []
    if include_web_search:
        output.append(
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "sources": [{"url": "https://example.com/community"}]
                },
            }
        )
    content = []
    if output_text is not None:
        content.append({"type": "output_text", "text": output_text})
    if refusal:
        content.append(
            {"type": "refusal", "refusal": "Private refusal content"}
        )
    if content:
        output.append(
            {
                "type": "message",
                "status": status,
                "content": content,
            }
        )
    return SimpleNamespace(
        id="resp_test_123",
        status=status,
        incomplete_details=(
            {"reason": incomplete_reason}
            if incomplete_reason
            else None
        ),
        usage={
            "input_tokens": 4100,
            "output_tokens": 1700,
            "total_tokens": 5800,
        },
        output=output,
    )


def candidate(
    *,
    name="Example Technology",
    website="https://example.com",
    evidence_url="https://example.com/community",
    industry="Technology",
    contact=None,
    mission_score=18,
):
    return SponsorProspectCandidate(
        company_name=name,
        website=website,
        location="Durham, NC",
        industry=industry,
        why_fits="Its services align with the initiative.",
        relevant_connection="The company has a documented local program.",
        verified_information=[
            VerifiedFact(
                statement="The company documents a local program.",
                source_url=evidence_url,
            )
        ],
        why_recommended="Documented community activity supports consideration.",
        organization_fit="The local program aligns with the mission.",
        recommended_ask="Provide technology services for the event.",
        contribution_type=ContributionType.SERVICE,
        recommended_need="Marketing",
        why_may_say_yes="The request aligns with its documented local program.",
        why_may_say_yes_evidence_urls=[
            evidence_url,
        ],
        geographic_relevance="It operates in Durham.",
        evidence_type=EvidenceType.COMMUNITY_INVOLVEMENT,
        evidence_sources=[
            ProspectEvidence(
                url=evidence_url,
                title="Community program",
                description="Official information about a local program.",
            )
        ],
        research_date=date(2026, 7, 24),
        confidence=ConfidenceLevel.HIGH,
        uncertainty=[],
        mission_fit_score=mission_score,
        audience_fit_score=17,
        geographic_fit_score=18,
        evidence_score=22,
        contactability_score=10,
        need_alignment_score=18,
        industry_alignment_score=13,
        ask_credibility_score=14,
        contact=contact,
    )


def test_real_research_schema_requires_public_evidence():
    with pytest.raises(ValidationError):
        SponsorProspectCandidate(
            company_name="Unsupported Company",
            website="https://example.com",
            location="Durham, NC",
            industry="Technology",
            why_fits="Possible fit",
            relevant_connection="Possible connection",
            geographic_relevance="Possible local presence",
            evidence_type=EvidenceType.STRATEGIC_FIT,
            evidence_sources=[],
            research_date=date.today(),
            confidence=ConfidenceLevel.LOW,
            mission_fit_score=1,
            audience_fit_score=1,
            geographic_fit_score=1,
            evidence_score=1,
            contactability_score=0,
            need_alignment_score=1,
            industry_alignment_score=1,
            ask_credibility_score=1,
        )


def test_uncited_evidence_is_rejected():
    accepted = validate_researched_prospects(
        SponsorResearchResult(prospects=[candidate()]),
        cited_urls={"https://different.example/source"},
        eligibility=eligibility(),
    )

    assert accepted == []


def test_missing_contact_is_valid_and_explicit():
    prospect = candidate(contact=None)

    accepted = validate_researched_prospects(
        SponsorResearchResult(prospects=[prospect]),
        cited_urls={"https://example.com/community"},
        eligibility=eligibility(),
    )

    assert accepted == [prospect]
    assert accepted[0].contact is None


def test_recommendation_strength_is_calculated_from_defined_factors():
    prospect = candidate()

    assert prospect.recommendation_strength_score == 90
    assert prospect.recommendation_strength.value == "High"
    assert prospect.strength_factors == {
        "sponsorship_need_alignment": 18,
        "industry_alignment": 13,
        "mission_and_audience_alignment": 18,
        "geographic_relevance": 14,
        "evidence_quality_and_recency": 13,
        "recommended_ask_credibility": 14,
    }


def test_verified_information_must_reference_candidate_evidence():
    values = candidate().model_dump()
    values["verified_information"] = [
        {
            "statement": "Unsupported fact",
            "source_url": "https://other.example/fact",
        }
    ]
    with pytest.raises(ValidationError):
        SponsorProspectCandidate.model_validate(values)


def test_why_may_say_yes_must_reference_candidate_evidence():
    values = candidate().model_dump()
    values["why_may_say_yes_evidence_urls"] = [
        "https://other.example/claim"
    ]
    with pytest.raises(ValidationError):
        SponsorProspectCandidate.model_validate(values)


def test_duplicate_websites_are_deduplicated_to_best_rank():
    lower = candidate(name="Example Tech", mission_score=10)
    higher = candidate(name="Example Technology Inc.", mission_score=20)

    accepted = validate_researched_prospects(
        SponsorResearchResult(prospects=[lower, higher]),
        cited_urls={"https://example.com/community"},
        eligibility=eligibility(),
    )

    assert accepted == [higher]


def test_deterministic_industry_exclusion_is_enforced():
    alcohol = candidate(
        name="Example Brewery",
        website="https://brewery.example",
        evidence_url="https://brewery.example/community",
        industry="Alcohol and Brewery",
    )

    accepted = validate_researched_prospects(
        SponsorResearchResult(prospects=[alcohol]),
        cited_urls={"https://brewery.example/community"},
        eligibility=eligibility("Middle school students"),
    )

    assert accepted == []


def test_ranking_uses_fit_evidence_geography_and_contactability():
    lower = candidate(
        name="Lower Ranked",
        website="https://lower.example",
        evidence_url="https://lower.example/source",
        mission_score=8,
    )
    higher = candidate(
        name="Higher Ranked",
        website="https://higher.example",
        evidence_url="https://higher.example/source",
        mission_score=20,
    )

    accepted = validate_researched_prospects(
        SponsorResearchResult(prospects=[lower, higher]),
        cited_urls={
            "https://lower.example/source",
            "https://higher.example/source",
        },
        eligibility=eligibility(),
    )

    assert accepted == [higher, lower]
    assert "Ranked" in higher.ranking_explanation


def test_contact_evidence_must_be_cited():
    prospect = candidate(
        contact=PublicBusinessContact(
            department="Community Relations",
            contact_url="https://example.com/contact",
            evidence_url="https://example.com/contact",
        )
    )

    accepted = validate_researched_prospects(
        SponsorResearchResult(prospects=[prospect]),
        cited_urls={"https://example.com/community"},
        eligibility=eligibility(),
    )

    assert accepted == []


def test_contact_details_require_an_evidence_url():
    with pytest.raises(ValidationError):
        PublicBusinessContact(
            department="Community Relations",
            contact_url="https://example.com/contact",
        )


def test_no_placeholder_fallback_when_research_has_no_credible_results(
    monkeypatch,
):
    monkeypatch.delenv(
        "OPENAI_SPONSOR_RESEARCH_MAX_OUTPUT_TOKENS",
        raising=False,
    )
    response = provider_response(
        SponsorResearchResult(prospects=[]).model_dump_json(),
    )
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response(response)
    )

    with pytest.raises(NoCredibleProspectsError) as raised:
        research_sponsor_category(
            SimpleNamespace(
                name="Example Organization",
                organization_type="Association",
                mission="Support education.",
                location="Durham, NC",
            ),
            SimpleNamespace(
                name="Conference",
                audience="Adults 21 and older",
                needs="Financial support",
                goals="Expand education",
            ),
            SimpleNamespace(
                category="Technology",
                research_direction="Research local technology firms",
                ideal_sponsor_profile="Community-oriented firms",
            ),
            [],
            eligibility(),
            client=request_client,
        )

    assert raised.value.reason_code == "no_candidates_returned"
    assert "No prospects were saved." in str(raised.value)
    request = (
        request_client.with_options.return_value.responses.with_raw_response.create
    )
    assert request.call_args.kwargs["model"] == "gpt-4.1-mini"
    assert request.call_args.kwargs["max_output_tokens"] == 8000
    assert "reasoning" not in request.call_args.kwargs
    assert request.call_args.kwargs["text"]["format"]["type"] == "json_schema"
    assert request.call_args.kwargs["text"]["format"]["strict"] is True
    assert "Return 5-10 real companies" in request.call_args.kwargs["input"]
    assert "additional\nsearches solely to find contact details" in (
        request.call_args.kwargs["input"]
    )


def test_valid_max_output_tokens_environment_value_is_used(monkeypatch):
    monkeypatch.setenv("OPENAI_SPONSOR_RESEARCH_MAX_OUTPUT_TOKENS", "5200")
    response = provider_response(
        SponsorResearchResult(prospects=[]).model_dump_json(),
    )
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response(response)
    )

    with pytest.raises(NoCredibleProspectsError):
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
            client=request_client,
        )

    request = (
        request_client.with_options.return_value.responses.with_raw_response.create
    )
    assert request.call_args.kwargs["max_output_tokens"] == 5200


@pytest.mark.parametrize("value", ["not-an-integer", "0", "-25"])
def test_invalid_max_output_tokens_environment_falls_back(
    monkeypatch,
    value,
):
    monkeypatch.setenv("OPENAI_SPONSOR_RESEARCH_MAX_OUTPUT_TOKENS", value)

    assert sponsor_research_max_output_tokens() == 8000


def test_web_search_source_collection_uses_citations_and_sources():
    response = SimpleNamespace(
        output=[
            {
                "type": "message",
                "content": [
                    {
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.com/source?tracking=1",
                            }
                        ]
                    }
                ],
            }
        ]
    )

    assert collect_web_search_source_urls(response) == {
        "https://example.com/source"
    }


def test_missing_api_key_fails_before_research(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SponsorResearchUnavailableError):
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
        )


def test_unexpected_sdk_failure_is_sanitized():
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.side_effect = (
        RuntimeError("sensitive provider response")
    )

    with pytest.raises(
        SponsorResearchError,
        match="Sponsor research returned an invalid result.",
    ) as raised:
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
            client=request_client,
        )

    assert "sensitive provider response" not in str(raised.value)


def test_incomplete_response_is_classified_before_pydantic(
    monkeypatch,
    caplog,
):
    private_output = (
        '{"prospects":[{"company_name":"Do Not Log This Company"'
    )
    response = provider_response(
        private_output,
        status="incomplete",
        incomplete_reason="max_output_tokens",
        include_web_search=True,
    )
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response(response)
    )
    parse = MagicMock()
    monkeypatch.setattr(SponsorResearchResult, "model_validate_json", parse)
    caplog.set_level("ERROR")

    with pytest.raises(
        SponsorResearchError,
        match="Sponsor research returned an invalid result.",
    ):
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
            client=request_client,
        )

    assert "response_id=resp_test_123" in caplog.text
    assert "response_status=incomplete" in caplog.text
    assert "incomplete_reason=max_output_tokens" in caplog.text
    assert "input_tokens=4100" in caplog.text
    assert "output_tokens=1700" in caplog.text
    assert "total_tokens=5800" in caplog.text
    assert "web_search_call_present=True" in caplog.text
    assert (
        f"output_text_character_count={len(private_output)}"
        in caplog.text
    )
    assert private_output not in caplog.text
    assert "Do Not Log This Company" not in caplog.text
    parse.assert_not_called()


def test_completed_response_with_web_search_parses_and_validates():
    prospect = candidate()
    response = provider_response(
        SponsorResearchResult(
            prospects=[prospect]
        ).model_dump_json(),
        include_web_search=True,
    )
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response(response)
    )

    result = research_sponsor_category(
        SimpleNamespace(
            name="Example Organization",
            organization_type="Association",
            mission="Support education.",
            location="Durham, NC",
        ),
        SimpleNamespace(
            name="Conference",
            audience="Adults 21 and older",
            needs="Marketing",
            goals="Expand education",
            sponsorship_needs_json='["Marketing"]',
        ),
        SimpleNamespace(
            category="Technology",
            research_direction="Research local technology firms",
            ideal_sponsor_profile="Community-oriented firms",
        ),
        [],
        eligibility(),
        client=request_client,
    )

    assert result == [prospect]


def test_completed_malformed_json_keeps_customer_error_safe(caplog):
    private_output = '{"prospects":[{"company_name":"Do Not Log"}'
    response = provider_response(private_output)
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response(response)
    )
    caplog.set_level("ERROR")

    with pytest.raises(
        SponsorResearchError,
        match="Sponsor research returned an invalid result.",
    ):
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
            client=request_client,
        )

    assert "exception_type=ValidationError" in caplog.text
    assert "json_invalid" in caplog.text
    assert private_output not in caplog.text
    assert "Do Not Log" not in caplog.text


def test_completed_response_without_output_text_is_handled_safely(caplog):
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response(provider_response())
    )
    caplog.set_level("ERROR")

    with pytest.raises(
        SponsorResearchError,
        match="Sponsor research returned an invalid result.",
    ):
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
            client=request_client,
        )

    assert "exception_type=MissingOutputText" in caplog.text


def test_refusal_response_is_not_parsed_or_logged(monkeypatch, caplog):
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response(provider_response(refusal=True))
    )
    parse = MagicMock()
    monkeypatch.setattr(SponsorResearchResult, "model_validate_json", parse)
    caplog.set_level("ERROR")

    with pytest.raises(
        SponsorResearchError,
        match="Sponsor research returned an invalid result.",
    ):
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
            client=request_client,
        )

    assert "exception_type=ProviderRefusal" in caplog.text
    assert "refusal_present=True" in caplog.text
    assert "Private refusal content" not in caplog.text
    parse.assert_not_called()


def test_openai_timeout_is_classified_and_sanitized():
    request_client = MagicMock()
    request_client.with_options.return_value.responses.with_raw_response.create.side_effect = (
        APITimeoutError(httpx.Request("POST", "https://api.openai.com"))
    )

    with pytest.raises(SponsorResearchUnavailableError) as raised:
        research_sponsor_category(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            [],
            eligibility(),
            client=request_client,
        )

    assert raised.value.reason_code == "openai_timeout"
    assert str(raised.value) == (
        "Sponsor research took too long to complete. Please try again."
    )
    assert raised.value.__cause__.__class__ is APITimeoutError

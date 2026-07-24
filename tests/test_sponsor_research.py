"""Tests for evidence-backed sponsor web research."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_research import (
    ConfidenceLevel,
    EvidenceType,
    NoCredibleProspectsError,
    ProspectEvidence,
    PublicBusinessContact,
    SponsorProspectCandidate,
    SponsorResearchResult,
    SponsorResearchError,
    SponsorResearchUnavailableError,
    collect_web_search_source_urls,
    research_sponsor_category,
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


def test_no_placeholder_fallback_when_research_has_no_credible_results():
    response = SimpleNamespace(
        output_parsed=SponsorResearchResult(prospects=[]),
        output=[],
    )
    request_client = MagicMock()
    request_client.with_options.return_value.responses.parse.return_value = (
        response
    )

    with pytest.raises(NoCredibleProspectsError):
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
    request_client.with_options.return_value.responses.parse.side_effect = (
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

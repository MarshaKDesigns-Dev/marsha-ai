"""Evidence-backed web research for approved sponsor categories."""

from __future__ import annotations

import os
from datetime import date
from enum import Enum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from services.sponsor_eligibility import SponsorEligibilityAnalysis
from services.sponsor_eligibility_gate import evaluate_category_research


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
SPONSOR_RESEARCH_TIMEOUT_SECONDS = 90.0


class SponsorResearchError(RuntimeError):
    """Controlled sponsor-research failure."""


class SponsorResearchUnavailableError(SponsorResearchError):
    """Raised when the research service cannot be used."""


class NoCredibleProspectsError(SponsorResearchError):
    """Raised when no evidence-backed prospects pass validation."""


class EvidenceType(str, Enum):
    VERIFIED_SPONSORSHIP = "verified_sponsorship"
    COMMUNITY_INVOLVEMENT = "community_involvement"
    STRATEGIC_FIT = "strategic_fit"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def _public_url(value: str) -> str:
    value = str(value or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A public HTTP or HTTPS URL is required.")
    return value


class ProspectEvidence(BaseModel):
    """One public source supporting a prospect recommendation."""

    model_config = ConfigDict(frozen=True)

    url: str
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=1000)

    _validate_url = field_validator("url")(_public_url)


class PublicBusinessContact(BaseModel):
    """Publicly verified contact information, when available."""

    model_config = ConfigDict(frozen=True)

    name: str | None = None
    title: str | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None
    contact_url: str | None = None
    evidence_url: str | None = None

    @field_validator("contact_url", "evidence_url")
    @classmethod
    def validate_optional_url(cls, value: str | None) -> str | None:
        return _public_url(value) if value else None

    @model_validator(mode="after")
    def require_evidence_for_contact_details(self):
        details = (
            self.name,
            self.title,
            self.department,
            self.email,
            self.phone,
            self.contact_url,
        )
        if any(details) and not self.evidence_url:
            raise ValueError(
                "Public contact details require a supporting evidence URL."
            )
        return self


class SponsorProspectCandidate(BaseModel):
    """Typed, evidence-backed company returned by web research."""

    model_config = ConfigDict(frozen=True)

    company_name: str = Field(min_length=1, max_length=300)
    website: str
    location: str = Field(min_length=1, max_length=300)
    industry: str = Field(min_length=1, max_length=200)
    why_fits: str = Field(min_length=1, max_length=2000)
    relevant_connection: str = Field(min_length=1, max_length=2000)
    geographic_relevance: str = Field(min_length=1, max_length=1000)
    evidence_type: EvidenceType
    evidence_sources: list[ProspectEvidence] = Field(min_length=1)
    research_date: date
    confidence: ConfidenceLevel
    uncertainty: list[str] = Field(default_factory=list)
    mission_fit_score: int = Field(ge=0, le=20)
    audience_fit_score: int = Field(ge=0, le=20)
    geographic_fit_score: int = Field(ge=0, le=20)
    evidence_score: int = Field(ge=0, le=25)
    contactability_score: int = Field(ge=0, le=15)
    contact: PublicBusinessContact | None = None

    _validate_website = field_validator("website")(_public_url)

    @property
    def ranking_score(self) -> int:
        return (
            self.mission_fit_score
            + self.audience_fit_score
            + self.geographic_fit_score
            + self.evidence_score
            + self.contactability_score
        )

    @property
    def ranking_explanation(self) -> str:
        strongest = max(
            (
                ("mission fit", self.mission_fit_score, 20),
                ("audience fit", self.audience_fit_score, 20),
                ("geographic relevance", self.geographic_fit_score, 20),
                ("public evidence", self.evidence_score, 25),
                ("contactability", self.contactability_score, 15),
            ),
            key=lambda item: item[1] / item[2],
        )[0]
        return (
            f"Ranked {self.ranking_score}/100, led by {strongest}; "
            f"evidence is {self.confidence.value} confidence."
        )


class SponsorResearchResult(BaseModel):
    """Structured result returned from one category research request."""

    model_config = ConfigDict(frozen=True)

    prospects: list[SponsorProspectCandidate] = Field(
        default_factory=list,
        max_length=8,
    )


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


def _collect_urls(value: Any, *, trusted_context: bool = False) -> set[str]:
    """Collect URLs only from SDK citation and web-search source objects."""

    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")

    if isinstance(value, list):
        urls: set[str] = set()
        for item in value:
            urls.update(_collect_urls(item, trusted_context=trusted_context))
        return urls

    if not isinstance(value, dict):
        return set()

    item_type = value.get("type")
    trusted = trusted_context or item_type in {
        "url_citation",
        "web_search_call",
    }
    urls = set()
    if trusted and isinstance(value.get("url"), str):
        urls.add(_canonical_url(value["url"]))

    for key, item in value.items():
        child_trusted = trusted or key in {"annotations", "sources"}
        urls.update(_collect_urls(item, trusted_context=child_trusted))
    return urls


def collect_web_search_source_urls(response: Any) -> set[str]:
    """Return canonical source URLs exposed by the web-search response."""

    return _collect_urls(getattr(response, "output", []))


def validate_researched_prospects(
    result: SponsorResearchResult,
    *,
    cited_urls: set[str],
    eligibility: SponsorEligibilityAnalysis,
) -> list[SponsorProspectCandidate]:
    """Reject unsupported, excluded, or duplicate prospect candidates."""

    accepted: dict[str, SponsorProspectCandidate] = {}
    for candidate in result.prospects:
        source_urls = {
            _canonical_url(source.url)
            for source in candidate.evidence_sources
        }
        if not source_urls or not source_urls.issubset(cited_urls):
            continue

        if candidate.contact and candidate.contact.evidence_url:
            if _canonical_url(candidate.contact.evidence_url) not in cited_urls:
                continue

        eligibility_decision = evaluate_category_research(
            eligibility,
            type(
                "CandidateIndustry",
                (),
                {
                    "slug": candidate.industry,
                    "category": candidate.industry,
                },
            )(),
        )
        if not eligibility_decision.allowed:
            continue

        key = _canonical_url(candidate.website)
        existing = accepted.get(key)
        if existing is None or candidate.ranking_score > existing.ranking_score:
            accepted[key] = candidate

    return sorted(
        accepted.values(),
        key=lambda item: (-item.ranking_score, item.company_name.lower()),
    )


def research_sponsor_category(
    organization: Any,
    initiative: Any,
    category: Any,
    assets: list[Any],
    eligibility: SponsorEligibilityAnalysis,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> list[SponsorProspectCandidate]:
    """Research and validate real prospects using OpenAI web search."""

    if client is None and not os.getenv("OPENAI_API_KEY"):
        raise SponsorResearchUnavailableError(
            "Sponsor research is temporarily unavailable. Please contact support."
        )

    openai_client = client or OpenAI()
    asset_summary = [
        {
            "name": getattr(asset, "name", ""),
            "sponsor_value": (
                getattr(asset, "sponsor_value", "")
                or getattr(asset, "value", "")
            ),
        }
        for asset in assets
    ]
    exclusions = [
        {
            "industry": item.industry_label,
            "reason": item.reason_code,
        }
        for item in eligibility.excluded_industries
    ]

    prompt = f"""
Research real sponsor prospects for this approved sponsor category.

Organization:
- Name: {getattr(organization, "name", "")}
- Type: {getattr(organization, "organization_type", "")}
- Mission: {getattr(organization, "mission", "")}
- Geography: {getattr(organization, "location", "")}

Initiative:
- Name: {getattr(initiative, "name", "")}
- Audience: {getattr(initiative, "audience", "")}
- Sponsorship needs: {getattr(initiative, "needs", "")}
- Goals: {getattr(initiative, "goals", "")}

Approved category:
- Name: {getattr(category, "category", "")}
- Research direction: {getattr(category, "research_direction", "")}
- Ideal sponsor profile: {getattr(category, "ideal_sponsor_profile", "")}

Available sponsorship assets: {asset_summary}
Deterministic industry exclusions: {exclusions}

Use current public web sources. Return 3-8 real companies or organizations.
Every prospect must have at least one public source supporting its existence,
location, community connection, sponsorship evidence, or strategic fit.
Classify evidence as verified_sponsorship only when a source explicitly supports
sponsorship activity. Use community_involvement for verified community activity.
Use strategic_fit when evidence supports only business, geographic, audience, or
mission relevance. Never invent a company, program, partnership, contact, URL,
email, phone number, sponsorship, or citation. Omit any candidate that conflicts
with the exclusions. A public contact may be null when none is verified. Score
mission fit, audience fit, geography, evidence, and contactability independently.
Use today's actual date for research_date.
"""

    try:
        response = openai_client.with_options(
            timeout=SPONSOR_RESEARCH_TIMEOUT_SECONDS,
            max_retries=0,
        ).responses.parse(
            model=model or DEFAULT_MODEL,
            tools=[{"type": "web_search"}],
            include=["web_search_call.action.sources"],
            input=prompt,
            text_format=SponsorResearchResult,
        )
    except (
        APITimeoutError,
        APIConnectionError,
        AuthenticationError,
        APIError,
    ) as exc:
        raise SponsorResearchUnavailableError(
            "Sponsor research is temporarily unavailable. Please try again."
        ) from exc
    except Exception as exc:
        raise SponsorResearchError(
            "Sponsor research returned an invalid result."
        ) from exc

    parsed = response.output_parsed
    if not isinstance(parsed, SponsorResearchResult):
        raise SponsorResearchError(
            "Sponsor research returned an invalid result."
        )

    prospects = validate_researched_prospects(
        parsed,
        cited_urls=collect_web_search_source_urls(response),
        eligibility=eligibility,
    )
    if not prospects:
        raise NoCredibleProspectsError(
            "No credible sponsor prospects were found for this category."
        )
    return prospects

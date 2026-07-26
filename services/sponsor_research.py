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
from services.sponsor_preferences import evaluate_sponsor_preference
from services.sponsorship_context import (
    build_sponsorship_context,
    format_sponsorship_context,
)


DEFAULT_MODEL = os.getenv(
    "OPENAI_SPONSOR_RESEARCH_MODEL",
    "gpt-4.1-mini",
)
SPONSOR_RESEARCH_TIMEOUT_SECONDS = 90.0
SPONSOR_RESEARCH_MAX_PROSPECTS = 5


class SponsorResearchError(RuntimeError):
    """Controlled sponsor-research failure."""


class SponsorResearchUnavailableError(SponsorResearchError):
    """Raised when the research service cannot be used."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "research_service_unavailable",
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class NoCredibleProspectsError(SponsorResearchError):
    """Raised when no evidence-backed prospects pass validation."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "no_credible_prospects",
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class EvidenceType(str, Enum):
    VERIFIED_SPONSORSHIP = "verified_sponsorship"
    COMMUNITY_INVOLVEMENT = "community_involvement"
    STRATEGIC_FIT = "strategic_fit"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ContributionType(str, Enum):
    CASH_SPONSORSHIP = "Cash sponsorship"
    IN_KIND = "In-kind contribution"
    SERVICE = "Service contribution"
    SCHOLARSHIP = "Scholarship support"
    MEDIA = "Media partnership"
    COMMUNITY = "Community partnership"
    COMBINATION = "Justified combination"


class RecommendationStrength(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


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


class VerifiedFact(BaseModel):
    """One factual statement explicitly supported by cited research."""

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1, max_length=1000)
    source_url: str

    _validate_url = field_validator("source_url")(_public_url)


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
    verified_information: list[VerifiedFact] = Field(min_length=1)
    why_recommended: str = Field(min_length=1, max_length=2000)
    organization_fit: str = Field(min_length=1, max_length=2000)
    recommended_ask: str = Field(min_length=1, max_length=2000)
    contribution_type: ContributionType
    recommended_need: str | None = Field(default=None, max_length=200)
    recommended_asset_name: str | None = Field(default=None, max_length=200)
    why_may_say_yes: str = Field(min_length=1, max_length=2000)
    why_may_say_yes_evidence_urls: list[str] = Field(min_length=1)
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
    need_alignment_score: int = Field(ge=0, le=20)
    industry_alignment_score: int = Field(ge=0, le=15)
    ask_credibility_score: int = Field(ge=0, le=15)
    contact: PublicBusinessContact | None = None

    _validate_website = field_validator("website")(_public_url)
    _validate_say_yes_evidence = field_validator(
        "why_may_say_yes_evidence_urls",
    )(lambda values: [_public_url(value) for value in values])

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

    @property
    def strength_factors(self) -> dict[str, int]:
        """Return the fixed 100-point strength rubric.

        Need alignment (20), industry alignment (15), combined mission and
        audience alignment (20), geography (15), evidence quality/recency
        (15), and ask credibility (15) produce the score. Relationship and
        exclusion rules are deterministic eligibility gates and therefore
        cannot be offset by a high score.
        """

        mission_audience = round(
            (self.mission_fit_score + self.audience_fit_score) / 2
        )
        geography = round(self.geographic_fit_score * 15 / 20)
        evidence = round(self.evidence_score * 15 / 25)
        return {
            "sponsorship_need_alignment": self.need_alignment_score,
            "industry_alignment": self.industry_alignment_score,
            "mission_and_audience_alignment": mission_audience,
            "geographic_relevance": geography,
            "evidence_quality_and_recency": evidence,
            "recommended_ask_credibility": self.ask_credibility_score,
        }

    @property
    def recommendation_strength_score(self) -> int:
        return sum(self.strength_factors.values())

    @property
    def recommendation_strength(self) -> RecommendationStrength:
        score = self.recommendation_strength_score
        if score >= 75:
            return RecommendationStrength.HIGH
        if score >= 50:
            return RecommendationStrength.MEDIUM
        return RecommendationStrength.LOW

    @model_validator(mode="after")
    def require_supported_recommendation(self):
        source_urls = {
            _canonical_url(item.url)
            for item in self.evidence_sources
        }
        fact_urls = {
            _canonical_url(item.source_url)
            for item in self.verified_information
        }
        if not fact_urls.issubset(source_urls):
            raise ValueError(
                "Verified information must reference supplied evidence."
            )
        say_yes_urls = {
            _canonical_url(url)
            for url in self.why_may_say_yes_evidence_urls
        }
        if not say_yes_urls.issubset(source_urls):
            raise ValueError(
                "Why-may-say-yes evidence must reference supplied evidence."
            )
        if not self.recommended_need and not self.recommended_asset_name:
            raise ValueError(
                "A recommended ask must identify an approved need or asset."
            )
        return self


class SponsorResearchResult(BaseModel):
    """Structured result returned from one category research request."""

    model_config = ConfigDict(frozen=True)

    prospects: list[SponsorProspectCandidate] = Field(
        default_factory=list,
        max_length=SPONSOR_RESEARCH_MAX_PROSPECTS,
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
    organization: Any | None = None,
    initiative: Any | None = None,
    assets: list[Any] | None = None,
) -> list[SponsorProspectCandidate]:
    """Reject unsupported, excluded, or duplicate prospect candidates."""

    accepted: dict[str, SponsorProspectCandidate] = {}
    approved_needs = set(
        build_sponsorship_context(organization, initiative)[
            "structured_needs"
        ]
        if organization is not None and initiative is not None
        else []
    )
    approved_assets = {
        str(getattr(asset, "name", "") or "").strip()
        for asset in (assets or [])
        if getattr(asset, "is_active", True)
        and getattr(asset, "approval_status", "Approved") == "Approved"
    }
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

        if organization is not None and initiative is not None:
            preference = evaluate_sponsor_preference(
                candidate.company_name,
                organization,
                initiative,
            )
            if not preference.allowed:
                continue
            if (
                candidate.recommended_need not in approved_needs
                and candidate.recommended_asset_name not in approved_assets
            ):
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
    customer_context = format_sponsorship_context(
        organization,
        initiative,
    )
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

Structured research context:
{customer_context}

Approved category:
- Name: {getattr(category, "category", "")}
- Research direction: {getattr(category, "research_direction", "")}
- Ideal sponsor profile: {getattr(category, "ideal_sponsor_profile", "")}

Available sponsorship assets: {asset_summary}
Deterministic industry exclusions: {exclusions}

Use current public web sources. Return 3-5 real companies or organizations.
Every prospect must have at least one public source supporting its existence,
location, community connection, sponsorship evidence, or strategic fit.
Classify evidence as verified_sponsorship only when a source explicitly supports
sponsorship activity. Use community_involvement for verified community activity.
Use strategic_fit when evidence supports only business, geographic, audience, or
mission relevance. Never invent a company, program, partnership, contact, URL,
email, phone number, sponsorship, or citation. Omit any candidate that conflicts
with the exclusions. Include a public contact only when it is readily available
in the same sources used to verify the company; do not perform additional
searches solely to find contact details. A public contact may be null when none
is verified. Score mission fit, audience fit, geography, evidence, and
contactability independently. Use today's actual date for research_date.
Every recommendation must separately provide verified_information,
why_recommended, organization_fit, recommended_ask, contribution_type,
recommended_need or recommended_asset_name, why_may_say_yes, and
why_may_say_yes_evidence_urls.
Verified information must cite one of the returned evidence URLs. Explanations
are Marsha AI assessments and must not present inference as verified fact.
Why-may-say-yes evidence URLs must cite the public evidence supporting that
specific assessment.
The recommended ask must match one of the structured sponsorship needs or one
of the approved assets. Dream sponsors guide research but never replace public
evidence. Never-contact, current-sponsor, existing-relationship, and
already-contacted rules override recommendations. Score need alignment,
industry alignment, and ask credibility independently; recommendation strength
is calculated by the application, not by the model.
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
    except APITimeoutError as exc:
        raise SponsorResearchUnavailableError(
            (
                "Sponsor research took too long to complete. Please try "
                "again."
            ),
            reason_code="openai_timeout",
        ) from exc
    except APIConnectionError as exc:
        raise SponsorResearchUnavailableError(
            "Sponsor research could not connect to the research service.",
            reason_code="openai_connection_error",
        ) from exc
    except AuthenticationError as exc:
        raise SponsorResearchUnavailableError(
            "Sponsor research is not configured correctly.",
            reason_code="openai_authentication_error",
        ) from exc
    except APIError as exc:
        raise SponsorResearchUnavailableError(
            "The sponsor research service is temporarily unavailable.",
            reason_code="openai_api_error",
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

    parsed_prospect_count = len(parsed.prospects)
    cited_urls = collect_web_search_source_urls(response)
    if parsed_prospect_count == 0:
        raise NoCredibleProspectsError(
            (
                "The research service found no companies with enough "
                "credible public evidence for this category. No prospects "
                "were saved."
            ),
            reason_code="no_candidates_returned",
        )
    if not cited_urls:
        raise NoCredibleProspectsError(
            (
                "The research service returned potential companies, but "
                "their public evidence could not be verified. No prospects "
                "were saved."
            ),
            reason_code="web_evidence_not_returned",
        )

    prospects = validate_researched_prospects(
        parsed,
        cited_urls=cited_urls,
        eligibility=eligibility,
        organization=organization,
        initiative=initiative,
        assets=assets,
    )
    if not prospects:
        raise NoCredibleProspectsError(
            (
                "Potential companies were found, but none passed the "
                "evidence and sponsor-eligibility checks. No prospects "
                "were saved."
            ),
            reason_code="candidates_failed_validation",
        )
    return prospects

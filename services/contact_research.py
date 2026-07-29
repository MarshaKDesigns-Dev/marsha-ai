"""Structured, evidence-gated results for contact discovery."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from enum import Enum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from openai import OpenAI
from openai.lib._parsing._responses import type_to_text_format_param
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from extensions import db
from services.sponsor_research import (
    DEFAULT_MODEL,
    SPONSOR_RESEARCH_TIMEOUT_SECONDS,
    _response_diagnostics,
    _response_output_text,
    collect_web_search_source_urls,
    sponsor_research_max_output_tokens,
)


class ContactResearchError(RuntimeError):
    """Controlled Contact Discovery failure."""

    def __init__(
        self,
        message: str,
        *,
        provider_response_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_response_id = provider_response_id
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class ContactResearchResultType(str, Enum):
    """Supported outcomes from one contact-discovery attempt."""

    NAMED_CONTACT = "named_contact"
    GENERAL_CONTACT = "general_contact"
    NO_CONTACT = "no_contact"


NULL_LIKE_CONTACT_VALUES = {
    "",
    "null",
    "none",
    "n/a",
    "not available",
}

GENERAL_CONTACT_NAME_LABELS = {
    "contact us",
    "general contact",
    "general inquiries",
    "main office",
    "customer service",
    "information",
}


def _public_url(value: str) -> str:
    normalized = str(value or "").strip()
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A public HTTP or HTTPS URL is required.")
    return normalized


class ContactResearchResult(BaseModel):
    """A verified contact, verified general route, or no-contact outcome."""

    model_config = ConfigDict(frozen=True)

    contact_name: str | None = None
    title: str | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None
    contact_url: str | None = None
    linkedin_url: str | None = None
    why_this_contact: str = Field(min_length=1, max_length=2000)
    confidence: str = Field(min_length=1, max_length=100)
    evidence_urls: list[str] = Field(default_factory=list)
    result_type: ContactResearchResultType

    @field_validator(
        "contact_name",
        "title",
        "department",
        "email",
        "phone",
        "contact_url",
        "linkedin_url",
        mode="before",
    )
    @classmethod
    def normalize_optional_detail(cls, value):
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.lower() in NULL_LIKE_CONTACT_VALUES:
                return None
            return normalized
        return value

    @field_validator("contact_url", "linkedin_url")
    @classmethod
    def validate_optional_public_url(cls, value: str | None) -> str | None:
        return _public_url(value) if value else None

    @field_validator("evidence_urls")
    @classmethod
    def validate_evidence_urls(cls, values: list[str]) -> list[str]:
        return [_public_url(value) for value in values]

    @model_validator(mode="after")
    def validate_result_contract(self):
        contact_details = (
            self.contact_name,
            self.title,
            self.department,
            self.email,
            self.phone,
            self.contact_url,
            self.linkedin_url,
        )
        has_contact_details = any(contact_details)

        if has_contact_details and not self.evidence_urls:
            raise ValueError(
                "Populated contact details require public evidence."
            )

        if self.result_type == ContactResearchResultType.NAMED_CONTACT:
            if not self.contact_name:
                raise ValueError("A named contact requires contact_name.")

        elif self.result_type == ContactResearchResultType.GENERAL_CONTACT:
            if self.contact_name:
                raise ValueError(
                    "A general contact must not identify a named person."
                )
            if not any((self.email, self.phone, self.contact_url)):
                raise ValueError(
                    "A general contact requires an email, phone, or "
                    "contact URL."
                )

        elif has_contact_details:
            raise ValueError(
                "A no-contact result must not contain contact details."
            )

        return self


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


def _official_domain(value: str | None) -> str:
    """Return only the hostname used to identify an organization."""

    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    return parsed.hostname or ""


def _normalize_general_contact_payload(
    payload: Any,
    *,
    sponsor_name: str,
) -> Any:
    """Remove only known non-person labels from general-contact names."""

    if not isinstance(payload, dict):
        return payload
    if str(payload.get("result_type", "")).strip() != "general_contact":
        return payload

    contact_name = payload.get("contact_name")
    if not isinstance(contact_name, str):
        return payload

    normalized_name = contact_name.strip().casefold()
    normalized_sponsor = str(sponsor_name or "").strip().casefold()
    if (
        normalized_name in GENERAL_CONTACT_NAME_LABELS
        or normalized_name == normalized_sponsor
    ):
        payload = dict(payload)
        payload["contact_name"] = None
    return payload


def _unwrap_contact_url(value: Any) -> Any:
    """Extract one URL only from explicitly supported whole-value wrappers."""

    if not isinstance(value, str):
        return value
    stripped = value.strip()
    url_count = len(
        re.findall(r"https?://", stripped, flags=re.IGNORECASE)
    )
    if url_count > 1:
        raise ValueError("A contact URL value must contain exactly one URL.")
    if url_count == 0:
        return stripped

    candidate = stripped
    if (
        (candidate.startswith("(") and candidate.endswith(")"))
        or (candidate.startswith("<") and candidate.endswith(">"))
        or (candidate.startswith('"') and candidate.endswith('"'))
        or (candidate.startswith("'") and candidate.endswith("'"))
    ):
        candidate = candidate[1:-1].strip()

    markdown = re.fullmatch(
        r"\[[^\]\r\n]+\]\((https?://[^\s]+)\)",
        candidate,
        flags=re.IGNORECASE,
    )
    if markdown:
        return markdown.group(1)
    if re.fullmatch(r"https?://[^\s]+", candidate, flags=re.IGNORECASE):
        return candidate
    raise ValueError(
        "A contact URL must be a raw URL or a supported whole-value wrapper."
    )


def _normalize_contact_url_payload(payload: Any) -> Any:
    """Normalize supported URL wrappers without changing URL components."""

    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    for field_name in ("contact_url", "linkedin_url"):
        if field_name in normalized:
            normalized[field_name] = _unwrap_contact_url(
                normalized[field_name]
            )
    evidence_urls = normalized.get("evidence_urls")
    if isinstance(evidence_urls, list):
        normalized["evidence_urls"] = [
            _unwrap_contact_url(value)
            for value in evidence_urls
        ]
    return normalized


def _collect_exact_web_search_source_urls(
    value: Any,
    *,
    trusted_context: bool = False,
) -> set[str]:
    """Collect exact provider source URLs without rewriting them."""

    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, list):
        urls: set[str] = set()
        for item in value:
            urls.update(
                _collect_exact_web_search_source_urls(
                    item,
                    trusted_context=trusted_context,
                )
            )
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
        urls.add(value["url"])
    for key, item in value.items():
        urls.update(
            _collect_exact_web_search_source_urls(
                item,
                trusted_context=trusted or key in {"annotations", "sources"},
            )
        )
    return urls


def _reconcile_contact_evidence(
    payload: Any,
    *,
    cited_urls_exact: set[str],
) -> Any:
    """Remove blank evidence and reuse only exactly cited contact URLs."""

    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    evidence_urls = normalized.get("evidence_urls")
    if not isinstance(evidence_urls, list):
        return normalized

    reconciled = []
    seen = set()
    for value in evidence_urls:
        if (
            isinstance(value, str)
            and value.strip().casefold() in NULL_LIKE_CONTACT_VALUES
        ):
            continue
        if value not in seen:
            reconciled.append(value)
            seen.add(value)

    if not reconciled:
        for field_name in ("contact_url", "linkedin_url"):
            candidate = normalized.get(field_name)
            if (
                isinstance(candidate, str)
                and candidate in cited_urls_exact
                and candidate not in seen
            ):
                reconciled.append(candidate)
                seen.add(candidate)
    normalized["evidence_urls"] = reconciled
    return normalized


def _validate_contact_research_output(
    output_text: str,
    *,
    sponsor_name: str,
    cited_urls_exact: set[str] | None = None,
) -> ContactResearchResult:
    """Apply narrow general-contact normalization before full validation."""

    try:
        payload = json.loads(output_text)
    except (TypeError, ValueError):
        return ContactResearchResult.model_validate_json(output_text)
    payload = _normalize_contact_url_payload(payload)
    payload = _reconcile_contact_evidence(
        payload,
        cited_urls_exact=cited_urls_exact or set(),
    )
    return ContactResearchResult.model_validate(
        _normalize_general_contact_payload(
            payload,
            sponsor_name=sponsor_name,
        )
    )


def _context_record(model, record_id):
    return db.session.get(model, record_id) if record_id else None


def _failure(
    exception: Exception,
    *,
    response: Any | None = None,
) -> ContactResearchError:
    diagnostics = _response_diagnostics(response)
    return ContactResearchError(
        f"{type(exception).__name__}: {exception}",
        provider_response_id=diagnostics["response_id"],
        input_tokens=diagnostics["input_tokens"],
        output_tokens=diagnostics["output_tokens"],
    )


def research_opportunity_contact(
    opportunity: Any,
    client: OpenAI | None = None,
) -> ContactResearchResult:
    """Find one evidence-backed public contact route for an Opportunity."""

    if client is None and not os.getenv("OPENAI_API_KEY"):
        raise ContactResearchError(
            "Contact research is temporarily unavailable."
        )

    from app import (
        Organization,
        SponsorProspect,
        SponsorshipAsset,
        SponsorshipInitiative,
    )

    organization = _context_record(
        Organization,
        getattr(opportunity, "organization_id", None),
    )
    initiative = _context_record(
        SponsorshipInitiative,
        getattr(opportunity, "initiative_id", None),
    )
    asset = _context_record(
        SponsorshipAsset,
        getattr(opportunity, "sponsorship_asset_id", None),
    )
    prospect = _context_record(
        SponsorProspect,
        getattr(opportunity, "sponsor_prospect_id", None),
    )
    sponsor_name = (
        getattr(prospect, "company_name", None)
        or getattr(opportunity, "recommended_target", None)
        or getattr(opportunity, "parent_prospect", "")
    )
    sponsor_domain = _official_domain(
        getattr(prospect, "website", "") if prospect else ""
    )
    sponsor_location = getattr(prospect, "location", "") if prospect else ""

    prompt = f"""
Find the best verified public communication route for this already-approved
sponsor opportunity.

The Sponsor Research Worker has already determined that this organization is
worth pursuing. Do not determine, re-evaluate, or re-prove sponsorship
eligibility, strategic fit, willingness to sponsor, or whether the organization
sponsors external events. Contact Discovery is responsible only for finding the
best verified way to reach the approved organization.

Sponsor organization:
- Name: {sponsor_name}
- Known official domain (identity only): {sponsor_domain}
- Known geography: {sponsor_location}

Customer context:
- Organization: {getattr(organization, "name", "")}
- Organization location: {getattr(organization, "location", "")}
- Mission: {getattr(organization, "mission", "")}
- Initiative: {getattr(initiative, "name", "")}
- Sponsorship asset: {getattr(asset, "name", "")}
- Opportunity category: {getattr(opportunity, "category", "")}

Conduct a new web search for the organization's current official communication
routes. Do not reuse URLs from prior sponsor research. Search official public
sources only, prioritizing:
1. Official organization Contact Us page
2. Sponsorship contact
3. Partnerships contact
4. Community Relations contact
5. Corporate Giving contact
6. Marketing contact
7. Development contact
8. Staff directory
9. Leadership directory
10. General inquiry email
11. General phone number

Never invent or infer a person, title, department, email address, phone number,
URL, or relationship. Every populated contact field must be directly supported
by at least one exact public HTTP/HTTPS URL returned by the current web search.
Return evidence URLs exactly as the provider returned them. Do not invent,
reconstruct, shorten, canonicalize, or substitute URLs. Do not return a URL
merely because it is predictable from the organization's domain. Every evidence
URL must be copied exactly from the current provider web-search citations or
source list.

Return evidence_urls as a JSON array of raw URL strings only. Each item must
begin directly with http:// or https://. Do not use Markdown links. Do not
include brackets, parentheses, labels, citation text, bullets, or surrounding
punctuation. Preserve the complete provider-returned URL, including its query
string.

Never return empty strings inside evidence_urls. When no evidence URL exists,
return an empty JSON array. Every populated contact_url or linkedin_url must
also appear in evidence_urls using the exact same raw provider-returned URL.
Do not omit evidence_urls for named_contact or general_contact. If no
provider-supported evidence exists, return no_contact.

contact_name is only for the full name of a specific human being. Never put the
organization name, a department, office, page title, or contact label in
contact_name. Labels such as Contact Us, General Contact, Main Office, Customer
Service, or Information are not people.

For result_type="general_contact", always return contact_name as JSON null,
title as JSON null, and linkedin_url as JSON null. Use department only when a
verified department is identified. Use contact_url for an official Contact Us
or general inquiry page.

Prefer a verified named contact in the priority areas above. Use
result_type="named_contact" only for a verified named person supported by
current provider evidence.

If no named or departmental contact is publicly verified, use
result_type="general_contact" for an official general email, phone number, or
contact page supported by current provider evidence. Official Contact Us pages,
staff directories, department pages, and general inquiry pages are valid
communication-route evidence. A general-contact source does not need to prove
sponsorship eligibility or outward-facing sponsorship activity.

Use result_type="no_contact" only when no verified public communication route
is returned by the current search. Return no contact details and an empty
evidence_urls list.
Use today's actual date, {date.today().isoformat()}, only as research context.
"""

    try:
        raw_response = (client or OpenAI()).with_options(
            timeout=SPONSOR_RESEARCH_TIMEOUT_SECONDS,
            max_retries=0,
        ).responses.with_raw_response.create(
            model=DEFAULT_MODEL,
            max_output_tokens=sponsor_research_max_output_tokens(),
            tools=[{"type": "web_search"}],
            include=["web_search_call.action.sources"],
            input=prompt,
            text={
                "format": type_to_text_format_param(ContactResearchResult)
            },
        )
        response = raw_response.parse()
    except Exception as exc:
        raise _failure(exc, response=locals().get("response")) from exc

    diagnostics = _response_diagnostics(
        response,
        http_status=getattr(raw_response, "status_code", None),
    )
    if (
        diagnostics["response_status"] != "completed"
        or diagnostics["refusal_present"]
    ):
        reason = RuntimeError(
            "OpenAI response was not usable: "
            f"status={diagnostics['response_status']!r}, "
            f"refusal_present={diagnostics['refusal_present']!r}."
        )
        raise _failure(reason, response=response)

    output_text = _response_output_text(response)
    if not output_text:
        raise _failure(
            ValueError("OpenAI response contained no output text."),
            response=response,
        )
    try:
        cited_urls_exact = _collect_exact_web_search_source_urls(
            getattr(response, "output", [])
        )
        result = _validate_contact_research_output(
            output_text,
            sponsor_name=sponsor_name,
            cited_urls_exact=cited_urls_exact,
        )
    except (ValidationError, ValueError) as exc:
        raise _failure(exc, response=response) from exc

    cited_urls = collect_web_search_source_urls(response)
    result_urls = {
        _canonical_url(url)
        for url in result.evidence_urls
    }
    if result_urls and not result_urls.issubset(cited_urls):
        rejected_urls = [
            url
            for url in result.evidence_urls
            if _canonical_url(url) not in cited_urls
        ]
        rejected_details = "; ".join(
            (
                f"{url!r}: not present in the provider's web-search "
                "citations or source list"
            )
            for url in rejected_urls
        )
        raise _failure(
            ValueError(
                "Contact evidence validation failed. Allowed evidence "
                "policy: every evidence URL must be a public HTTP/HTTPS "
                "URL returned in the provider's web_search_call citations "
                "or source list. Rejected evidence URLs: "
                f"{rejected_details}."
            ),
            response=response,
        )
    return result

"""Structured customer context used by sponsorship intelligence and research."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable


SPONSORSHIP_NEEDS = (
    "Cash Sponsorship",
    "Scholarships",
    "Venue",
    "Meeting Space",
    "Flowers",
    "Photography",
    "Videography",
    "Printing",
    "Marketing",
    "Transportation",
    "Hotels",
    "Catering",
    "Crowns",
    "Trophies",
    "Awards",
    "Hair",
    "Makeup",
    "Boutique/Fashion",
    "Jewelry",
    "Gift Bags",
    "Audio",
    "Lighting",
    "DJ",
    "Stage",
    "Volunteers",
    "Community Partners",
    "Colleges",
    "Government",
    "Media Partners",
    "Other",
)

GEOGRAPHIC_SCOPES = (
    "My City",
    "My County",
    "My State",
    "Southeast US",
    "Nationwide",
    "Radius",
)
GEOGRAPHIC_RADII = (10, 25, 50, 100)

INDUSTRY_MAPPING = {
    "Cash Sponsorship": ("corporate philanthropy", "financial services"),
    "Scholarships": ("education", "workforce development", "foundations"),
    "Venue": ("hospitality", "event venues", "commercial real estate"),
    "Meeting Space": ("coworking", "hospitality", "commercial real estate"),
    "Flowers": ("florists", "event design"),
    "Photography": ("photography", "creative services"),
    "Videography": ("video production", "creative services"),
    "Printing": ("printing", "signage", "promotional products"),
    "Marketing": ("marketing", "advertising", "public relations"),
    "Transportation": ("transportation", "automotive", "mobility", "logistics"),
    "Hotels": ("hospitality", "lodging", "tourism"),
    "Catering": ("restaurants", "catering", "food service"),
    "Crowns": ("jewelry", "pageant suppliers", "specialty retail"),
    "Trophies": ("awards", "engraving", "promotional products"),
    "Awards": ("awards", "engraving", "recognition products"),
    "Hair": ("beauty", "salons", "hair care"),
    "Makeup": ("beauty", "cosmetics", "personal care"),
    "Boutique/Fashion": ("fashion", "apparel", "specialty retail"),
    "Jewelry": ("jewelry", "accessories", "luxury retail"),
    "Gift Bags": ("retail", "consumer products", "promotional products"),
    "Audio": ("audio visual", "event production", "entertainment technology"),
    "Lighting": ("lighting", "event production", "entertainment technology"),
    "DJ": ("entertainment", "music", "event production"),
    "Stage": ("staging", "event production", "audio visual"),
    "Volunteers": ("employers", "service organizations", "community groups"),
    "Community Partners": ("nonprofits", "associations", "civic organizations"),
    "Colleges": ("higher education", "workforce development"),
    "Government": ("government", "economic development", "public agencies"),
    "Media Partners": ("media", "broadcasting", "publishing"),
}


def json_list(value: Any) -> list[str]:
    """Return a clean, unique list from JSON, a list, or newline text."""

    if isinstance(value, str):
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, ValueError):
            parsed = re.split(r"[\r\n,]+", value)
    elif isinstance(value, (list, tuple, set)):
        parsed = list(value)
    else:
        parsed = []

    result = []
    seen = set()
    for item in parsed if isinstance(parsed, list) else []:
        cleaned = str(item or "").strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def dump_list(values: Iterable[Any]) -> str:
    return json.dumps(json_list(list(values)), ensure_ascii=False)


def validate_needs(values: Iterable[Any]) -> list[str]:
    allowed = set(SPONSORSHIP_NEEDS)
    return [item for item in json_list(list(values)) if item in allowed]


def parse_multiline(value: str | None) -> list[str]:
    return json_list(value or "")


def mapped_industries(needs: Iterable[str]) -> list[str]:
    industries = []
    seen = set()
    for need in needs:
        for industry in INDUSTRY_MAPPING.get(need, ()):
            key = industry.casefold()
            if key not in seen:
                seen.add(key)
                industries.append(industry)
    return industries


def geographic_instruction(initiative: Any, organization: Any) -> str:
    scope = str(getattr(initiative, "geographic_scope", "") or "").strip()
    radius = getattr(initiative, "geographic_radius_miles", None)
    location = str(getattr(organization, "location", "") or "").strip()
    if scope == "Radius" and radius in GEOGRAPHIC_RADII:
        return f"Within {radius} miles of {location or 'the organization'}"
    return {
        "My City": f"The organization's city: {location}",
        "My County": f"The organization's county around {location}",
        "My State": f"The organization's state: {location}",
        "Southeast US": "The Southeast United States",
        "Nationwide": "Nationwide in the United States",
    }.get(scope, location or "Not provided")


def build_sponsorship_context(organization: Any, initiative: Any) -> dict[str, Any]:
    needs = json_list(getattr(initiative, "sponsorship_needs_json", "[]"))
    return {
        "mission": str(getattr(organization, "mission", "") or "").strip(),
        "organization_type": str(
            getattr(organization, "organization_type", "") or ""
        ).strip(),
        "structured_needs": needs,
        "other_needs": str(
            getattr(initiative, "sponsorship_needs_other", "") or ""
        ).strip(),
        "needs_notes": str(
            getattr(initiative, "sponsorship_needs_notes", "") or ""
        ).strip(),
        "legacy_needs": str(getattr(initiative, "needs", "") or "").strip(),
        "fundraising_goal": str(
            getattr(initiative, "fundraising_target", "") or ""
        ).strip(),
        "desired_sponsor_categories": json_list(
            getattr(initiative, "desired_sponsor_categories_json", "[]")
        ),
        "industry_mapping": mapped_industries(needs),
        "geographic_preference": geographic_instruction(
            initiative,
            organization,
        ),
        "dream_sponsors": json_list(
            getattr(initiative, "dream_sponsors_json", "[]")
        ),
        "current_sponsors": json_list(
            getattr(organization, "current_sponsors_json", "[]")
        ),
        "existing_relationships": json_list(
            getattr(organization, "existing_relationships_json", "[]")
        ),
        "businesses_already_contacted": json_list(
            getattr(organization, "businesses_already_contacted_json", "[]")
        ),
        "businesses_never_contact": json_list(
            getattr(organization, "businesses_never_contact_json", "[]")
        ),
        "community": str(getattr(initiative, "audience", "") or "").strip(),
        "strategy_top_priorities": str(
            getattr(initiative, "strategy_top_priorities", "") or ""
        ).strip(),
        "strategy_priority_sponsors": str(
            getattr(initiative, "strategy_priority_sponsors", "") or ""
        ).strip(),
        "strategy_success_beyond_fundraising": str(
            getattr(
                initiative,
                "strategy_success_beyond_fundraising",
                "",
            )
            or ""
        ).strip(),
        "strategy_concerns_constraints": str(
            getattr(initiative, "strategy_concerns_constraints", "") or ""
        ).strip(),
    }


def format_sponsorship_context(organization: Any, initiative: Any) -> str:
    """Return a stable prompt section shared by intelligence workers."""

    context = build_sponsorship_context(organization, initiative)
    return "\n".join(
        (
            f"Organization type: {context['organization_type'] or 'Not provided'}",
            f"Mission: {context['mission'] or 'Not provided'}",
            f"Community and audience: {context['community'] or 'Not provided'}",
            f"Fundraising goal: {context['fundraising_goal'] or 'Not provided'}",
            f"Structured sponsorship needs: {context['structured_needs']}",
            f"Other needs: {context['other_needs'] or 'None'}",
            f"Needs notes: {context['needs_notes'] or 'None'}",
            f"Legacy needs context: {context['legacy_needs'] or 'None'}",
            (
                "Desired sponsor categories: "
                f"{context['desired_sponsor_categories']}"
            ),
            f"Mapped industries: {context['industry_mapping']}",
            (
                "Geographic search preference: "
                f"{context['geographic_preference']}"
            ),
            f"Dream sponsors (guidance only): {context['dream_sponsors']}",
            f"Current sponsors: {context['current_sponsors']}",
            f"Existing relationships: {context['existing_relationships']}",
            (
                "Businesses already contacted: "
                f"{context['businesses_already_contacted']}"
            ),
            (
                "Businesses never contact: "
                f"{context['businesses_never_contact']}"
            ),
            (
                "Strategy Meeting — top three priorities: "
                f"{context['strategy_top_priorities'] or 'Not provided'}"
            ),
            (
                "Strategy Meeting — sponsors to pursue first: "
                f"{context['strategy_priority_sponsors'] or 'Not provided'}"
            ),
            (
                "Strategy Meeting — success beyond fundraising: "
                f"{context['strategy_success_beyond_fundraising'] or 'Not provided'}"
            ),
            (
                "Strategy Meeting — concerns or constraints: "
                f"{context['strategy_concerns_constraints'] or 'Not provided'}"
            ),
        )
    )

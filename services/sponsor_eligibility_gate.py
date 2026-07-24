"""Deterministic category-research access decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.sponsor_eligibility import (
    AudienceAgeContext,
    EligibilityStatus,
    SponsorEligibilityAnalysis,
)


@dataclass(frozen=True)
class CategoryResearchDecision:
    """Controlled decision returned before category research begins."""

    allowed: bool
    reason: str | None = None
    reason_code: str | None = None


_INDUSTRY_TERMS = {
    "alcohol": ("alcohol", "beer", "wine", "spirits", "brewery", "distillery"),
    "tobacco": ("tobacco", "cigarette", "cigar"),
    "vaping": ("vaping", "vape", "e-cigarette"),
    "cannabis": ("cannabis", "marijuana", "dispensary"),
    "gambling": ("gambling", "casino", "lottery"),
    "sports-betting": ("sports betting", "sportsbook"),
    "adult-entertainment": ("adult entertainment",),
    "firearms-weapons": ("firearm", "weapon", "gun"),
    "predatory-financial-products": (
        "payday loan",
        "title loan",
        "predatory financial",
    ),
    "other-age-inappropriate": ("age inappropriate",),
}


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _matches_exclusion(category: Any, industry_code: str, label: str) -> bool:
    category_text = _normalized(
        " ".join(
            (
                str(getattr(category, "slug", "")),
                str(getattr(category, "category", "")),
            )
        )
    )
    terms = _INDUSTRY_TERMS.get(
        industry_code,
        (_normalized(industry_code), _normalized(label)),
    )
    return any(
        term and _normalized(term) in category_text
        for term in terms
    )


def evaluate_category_research(
    analysis: SponsorEligibilityAnalysis | None,
    category: Any,
) -> CategoryResearchDecision:
    """Enforce persisted eligibility before category research."""

    if analysis is None:
        return CategoryResearchDecision(
            allowed=False,
            reason=(
                "Sponsor eligibility analysis is required before category "
                "research. Regenerate sponsorship intelligence first."
            ),
            reason_code="eligibility_analysis_required",
        )

    if (
        analysis.audience_age_context is AudienceAgeContext.UNCLEAR
        or "audience_age_context" in analysis.missing_information
    ):
        return CategoryResearchDecision(
            allowed=False,
            reason=(
                "Sponsor research is blocked until the audience age context "
                "is confirmed."
            ),
            reason_code="audience_age_context_required",
        )

    if (
        analysis.research_blocked
        or analysis.eligibility_status is EligibilityStatus.BLOCKED
    ):
        return CategoryResearchDecision(
            allowed=False,
            reason=(
                "Sponsor research is blocked until the eligibility "
                "requirements are resolved."
            ),
            reason_code="eligibility_requirements_unresolved",
        )

    for exclusion in analysis.excluded_industries:
        if _matches_exclusion(
            category,
            exclusion.industry_code,
            exclusion.industry_label,
        ):
            return CategoryResearchDecision(
                allowed=False,
                reason=(
                    "Research for this category is blocked by sponsor "
                    f"eligibility rules: {exclusion.industry_label}."
                ),
                reason_code=exclusion.reason_code,
            )

    return CategoryResearchDecision(allowed=True)

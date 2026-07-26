"""Deterministic organization relationship rules for sponsor discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.sponsorship_context import build_sponsorship_context


LEGAL_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "pllc",
}


def normalized_company_name(value: str) -> str:
    """Normalize exact company names without fuzzy matching."""

    words = re.findall(r"[a-z0-9]+", str(value or "").casefold())
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


@dataclass(frozen=True)
class SponsorPreferenceDecision:
    allowed: bool
    reason_code: str | None = None
    matched_name: str | None = None


def evaluate_sponsor_preference(
    company_name: str,
    organization: Any,
    initiative: Any,
) -> SponsorPreferenceDecision:
    """Apply reviewable exact-name rules; never silently fuzzy-match."""

    candidate_key = normalized_company_name(company_name)
    context = build_sponsorship_context(organization, initiative)
    rule_lists = (
        ("never_contact", context["businesses_never_contact"]),
        ("current_sponsor", context["current_sponsors"]),
        ("existing_relationship", context["existing_relationships"]),
        ("already_contacted", context["businesses_already_contacted"]),
    )
    for reason_code, names in rule_lists:
        for name in names:
            if candidate_key and candidate_key == normalized_company_name(name):
                return SponsorPreferenceDecision(
                    allowed=False,
                    reason_code=reason_code,
                    matched_name=name,
                )
    return SponsorPreferenceDecision(allowed=True)

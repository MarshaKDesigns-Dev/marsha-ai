"""Stable JSON serialization for deterministic sponsor eligibility results."""

from __future__ import annotations

import json

from pydantic import ValidationError

from services.sponsor_eligibility import SponsorEligibilityAnalysis


class SponsorEligibilitySerializationError(ValueError):
    """Raised when persisted eligibility data cannot be encoded or decoded."""


def serialize_sponsor_eligibility(
    analysis: SponsorEligibilityAnalysis | None,
) -> str | None:
    """Serialize a typed eligibility result as stable JSON."""

    if analysis is None:
        return None

    if not isinstance(analysis, SponsorEligibilityAnalysis):
        raise SponsorEligibilitySerializationError(
            "A SponsorEligibilityAnalysis instance is required."
        )

    try:
        return json.dumps(
            analysis.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise SponsorEligibilitySerializationError(
            "Sponsor eligibility analysis could not be serialized."
        ) from exc


def deserialize_sponsor_eligibility(
    serialized: str | None,
) -> SponsorEligibilityAnalysis | None:
    """Deserialize stored JSON into a validated eligibility result."""

    if serialized is None or not serialized.strip():
        return None

    try:
        value = json.loads(serialized)
        return SponsorEligibilityAnalysis.model_validate(value)
    except (TypeError, ValueError, ValidationError) as exc:
        raise SponsorEligibilitySerializationError(
            "Stored sponsor eligibility analysis is invalid."
        ) from exc

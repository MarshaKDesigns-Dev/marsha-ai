"""Deterministic prerequisites for beginning new sponsor research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from services.sponsor_eligibility import (
    AudienceAgeContext,
    EligibilityFacts,
)
from services.sponsor_eligibility_rules_v1 import (
    AudienceAgeContextRule,
    EligibilityRuleContext,
)


APPROVAL_STATUSES = frozenset({"Pending", "Approved", "Rejected"})


@dataclass(frozen=True)
class SponsorResearchReadiness:
    """A controlled decision about non-eligibility research prerequisites."""

    allowed: bool
    reason: str | None = None
    reason_code: str | None = None


def validate_approval_status(value: Any) -> str:
    """Return an allowed approval status or reject the value."""

    status = str(value or "").strip()
    if status not in APPROVAL_STATUSES:
        raise ValueError("Unsupported sponsorship asset approval status.")
    return status


def audience_age_context_is_clear(audience: Any) -> bool:
    """Use the versioned eligibility rule to validate meeting age context."""

    context = EligibilityRuleContext(
        facts=EligibilityFacts(audience=str(audience or "").strip())
    )
    effect = AudienceAgeContextRule().evaluate(context)
    return effect.age_context is not AudienceAgeContext.UNCLEAR


def strategy_meeting_is_complete(
    initiative: Any,
    intelligence: Any = None,
) -> bool:
    """Treat legacy generated intelligence as completed meeting context."""

    return bool(
        getattr(initiative, "strategy_meeting_completed_at", None)
        or intelligence is not None
    )


def evaluate_sponsor_research_readiness(
    initiative: Any,
    assets: Iterable[Any],
    *,
    intelligence: Any = None,
) -> SponsorResearchReadiness:
    """Require a completed meeting and at least one approved active asset."""

    if not strategy_meeting_is_complete(initiative, intelligence):
        return SponsorResearchReadiness(
            allowed=False,
            reason=(
                "Complete the Strategy Meeting before beginning sponsor "
                "research."
            ),
            reason_code="strategy_meeting_required",
        )

    approved = any(
        getattr(asset, "is_active", True)
        and getattr(asset, "approval_status", "Pending") == "Approved"
        for asset in assets
    )
    if not approved:
        return SponsorResearchReadiness(
            allowed=False,
            reason=(
                "Approve at least one sponsorship asset before beginning "
                "sponsor research."
            ),
            reason_code="approved_sponsorship_asset_required",
        )

    return SponsorResearchReadiness(allowed=True)

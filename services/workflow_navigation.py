"""Display-only workflow navigation derived from existing persisted facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from services.workflow_labels import workflow_label
from services.sponsor_research_readiness import strategy_meeting_is_complete


@dataclass(frozen=True)
class NavigationItem:
    key: str
    label: str
    endpoint: str
    icon: str
    state: str
    locked_reason: str | None = None


@dataclass(frozen=True)
class OpportunityProgressStep:
    key: str
    label: str
    state: str


def setup_is_complete(organization: Any, initiative: Any) -> bool:
    return bool(
        organization
        and initiative
        and (getattr(organization, "name", "") or "").strip()
        and (getattr(initiative, "name", "") or "").strip()
    )


def strategy_is_approved(
    initiative: Any,
    intelligence: Any,
    assets: Iterable[Any],
) -> bool:
    return bool(
        strategy_meeting_is_complete(initiative, intelligence)
        and intelligence is not None
        and any(
            getattr(asset, "is_active", True)
            and getattr(asset, "approval_status", "Pending") == "Approved"
            for asset in assets
        )
    )


def opportunity_needs_action(opportunity: Any, today: date) -> bool:
    stage = getattr(opportunity, "stage", None)
    if stage in {"Won", "Lost"}:
        return False
    if stage == "Sent":
        follow_up_date = getattr(opportunity, "follow_up_date", None)
        return bool(follow_up_date and follow_up_date <= today)
    return True


def build_primary_navigation(
    *,
    organization: Any = None,
    initiative: Any = None,
    intelligence: Any = None,
    assets: Iterable[Any] = (),
    opportunities: Iterable[Any] = (),
    today: date | None = None,
) -> tuple[NavigationItem, ...]:
    """Return the primary workflow destinations in progressive states."""

    current_date = today or date.today()
    asset_list = list(assets)
    opportunity_list = list(opportunities)
    setup_complete = setup_is_complete(organization, initiative)
    strategy_approved = bool(
        setup_complete
        and strategy_is_approved(initiative, intelligence, asset_list)
    )
    pipeline_created = bool(opportunity_list)
    pipeline_needs_action = any(
        opportunity_needs_action(item, current_date)
        for item in opportunity_list
    )

    if not setup_complete:
        current_key = "setup"
    elif not strategy_approved:
        current_key = "strategy"
    elif not pipeline_created:
        current_key = "research"
    elif pipeline_needs_action:
        current_key = "pipeline"
    else:
        current_key = "research"

    strategy_endpoint = (
        "strategy_work" if intelligence is not None else "strategy_meeting"
    )
    definitions = (
        ("setup", "Organization", "setup", "▦"),
        ("strategy", "Strategy", strategy_endpoint, "◎"),
        ("research", "Research", "research_worker", "♧"),
        ("pipeline", "Pipeline", "show_pipeline", "▽"),
    )
    items = []
    for key, label_key, endpoint, icon in definitions:
        locked_reason = None
        if key == "setup":
            state = "complete" if setup_complete else "current"
        elif key == "strategy":
            if not setup_complete:
                state = "locked"
                locked_reason = "Complete Organization Setup to unlock this stage."
            else:
                state = "complete" if strategy_approved else "current"
        elif key == "research":
            if not strategy_approved:
                state = "locked"
                locked_reason = (
                    "Approve the Sponsorship Strategy to unlock this stage."
                )
            elif pipeline_created and current_key != "research":
                state = "complete"
            else:
                state = "current"
        else:
            if not pipeline_created:
                state = "locked"
                locked_reason = (
                    "Save at least one sponsor to unlock the Sponsor Pipeline."
                )
            else:
                state = "current" if current_key == "pipeline" else "available"

        items.append(
            NavigationItem(
                key=key,
                label=workflow_label(label_key),
                endpoint=endpoint,
                icon=icon,
                state=state,
                locked_reason=locked_reason,
            )
        )
    return tuple(items)


def build_opportunity_progress(
    opportunity: Any,
) -> tuple[OpportunityProgressStep, ...]:
    """Return display-only progress for one Sponsor Opportunity."""

    stage = getattr(opportunity, "stage", None)
    outreach_exists = bool(
        getattr(opportunity, "outreach", None)
        or getattr(opportunity, "reviewed_message", None)
    )
    reviewed = bool(getattr(opportunity, "message_reviewed_at", None))
    approved = bool(getattr(opportunity, "message_approved_at", None))
    delivered = bool(
        stage
        in {
            "Sent",
            "Follow-Up Due",
            "Responded",
            "Meeting",
            "Proposal",
            "Won",
            "Lost",
        }
        or getattr(opportunity, "sent_date", None)
    )
    follow_up_finished = bool(
        getattr(opportunity, "follow_up_completed_at", None)
    )
    workflow_complete = stage in {"Won", "Lost"}

    completed = {
        "research": True,
        "preparation": outreach_exists,
        "review": reviewed,
        "ready": delivered,
        "follow_up": follow_up_finished or workflow_complete,
        "complete": workflow_complete,
    }
    if not completed["research"]:
        current_key = "research"
    elif not completed["preparation"]:
        current_key = "preparation"
    elif not completed["review"] or (not approved and not delivered):
        current_key = "review"
    elif not completed["ready"]:
        current_key = "ready"
    elif not completed["follow_up"]:
        current_key = "follow_up"
    elif workflow_complete:
        current_key = "complete"
    else:
        current_key = None

    definitions = (
        ("research", "Sponsor Research"),
        ("preparation", "Outreach Working"),
        ("review", "Message Review"),
        ("ready", "message_approved"),
        ("follow_up", "Follow-Up Due"),
        ("complete", "complete"),
    )
    return tuple(
        OpportunityProgressStep(
            key=key,
            label=workflow_label(label_key),
            state=(
                "complete"
                if completed[key] and key != current_key
                else "current"
                if key == current_key
                else "upcoming"
            ),
        )
        for key, label_key in definitions
    )

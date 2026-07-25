"""Deterministic, read-only status building for the Coordinator dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Iterable


ACTIVE_JOB_STATUSES = {"pending", "processing"}
OUTREACH_ACTIVE_STAGES = {
    "Sent",
    "Follow-Up Due",
    "Responded",
    "Meeting",
    "Proposal",
    "Won",
}


@dataclass(frozen=True)
class DashboardAction:
    """One existing application action exposed by the dashboard."""

    label: str = ""
    endpoint: str | None = None
    method: str = "GET"
    route_params: dict[str, Any] = field(default_factory=dict)
    form_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardPriority:
    """The single most important action currently waiting on the user."""

    title: str
    message: str
    level: str
    action: DashboardAction
    supporting_line: str | None = None


@dataclass(frozen=True)
class DashboardProgressStep:
    """One concise stage in the sponsorship workflow."""

    label: str
    status: str


@dataclass(frozen=True)
class DashboardWorker:
    """Current status and next action for one AI employee."""

    name: str
    status: str
    message: str
    action: DashboardAction
    detail_label: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class DashboardActivity:
    """One safe activity item derived from an existing record."""

    message: str
    occurred_at: datetime
    action: DashboardAction | None = None


@dataclass(frozen=True)
class DashboardView:
    """Complete presentation model for the Release 1 dashboard."""

    greeting: str
    days_remaining: int | None
    top_priority: DashboardPriority
    progress: tuple[DashboardProgressStep, ...]
    workers: tuple[DashboardWorker, ...]
    recent_activity: tuple[DashboardActivity, ...]
    pipeline_count: int
    sponsors_secured: int


def _first_name(sender_name: str | None) -> str:
    value = (sender_name or "").strip()
    return value.split()[0] if value else "there"


def _greeting(hour: int, sender_name: str | None) -> str:
    if hour < 12:
        salutation = "Good morning"
    elif hour < 18:
        salutation = "Good afternoon"
    else:
        salutation = "Good evening"
    return f"{salutation}, {_first_name(sender_name)}"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _latest_timestamp(record: Any) -> datetime | None:
    for attribute in (
        "updated_at",
        "completed_at",
        "generated_at",
        "created_at",
    ):
        value = _as_utc(getattr(record, attribute, None))
        if value is not None:
            return value
    return None


def _activity(
    message: str,
    record: Any,
    action: DashboardAction | None = None,
) -> DashboardActivity | None:
    occurred_at = _latest_timestamp(record)
    if occurred_at is None:
        return None
    return DashboardActivity(
        message=message,
        occurred_at=occurred_at,
        action=action,
    )


def _build_recent_activity(
    intelligence: Any,
    generation_job: Any,
    prospects: list[Any],
    opportunities: list[Any],
) -> tuple[DashboardActivity, ...]:
    items: list[DashboardActivity] = []

    if generation_job is not None:
        status = (getattr(generation_job, "status", "") or "").lower()
        messages = {
            "pending": "Strategy work was queued.",
            "processing": "The Strategy Worker started intelligence generation.",
            "completed": "The Strategy Worker completed intelligence generation.",
            "failed": "Strategy work needs attention.",
        }
        item = _activity(
            messages.get(status, "Strategy work was updated."),
            generation_job,
        )
        if item:
            items.append(item)

    if intelligence is not None:
        item = _activity(
            "Sponsorship intelligence is available.",
            intelligence,
        )
        if item:
            items.append(item)

    for prospect in prospects[:3]:
        company_name = (
            getattr(prospect, "company_name", None)
            or "A sponsor prospect"
        )
        category = (getattr(prospect, "category_slug", None) or "").replace(
            "_",
            " ",
        )
        message = f"{company_name} was added by sponsor research."
        if category:
            message = (
                f"{company_name} was added to {category.title()} research."
            )
        item = _activity(
            message,
            prospect,
            DashboardAction(
                label="Review research",
                endpoint="prospects",
                route_params={
                    "category": getattr(prospect, "category_slug", "")
                },
            ),
        )
        if item:
            items.append(item)

    for opportunity in opportunities[:4]:
        target = (
            getattr(opportunity, "recommended_target", None)
            or getattr(opportunity, "parent_prospect", None)
            or "An opportunity"
        )
        stage = getattr(opportunity, "stage", None) or "updated"
        item = _activity(
            f"{target} moved to {stage}.",
            opportunity,
            DashboardAction(
                label="Open opportunity",
                endpoint="opportunity_detail",
                route_params={
                    "opportunity_id": getattr(opportunity, "id", None)
                },
            ),
        )
        if item:
            items.append(item)

    return tuple(
        sorted(
            items,
            key=lambda item: item.occurred_at,
            reverse=True,
        )[:4]
    )


def _days_remaining(deadline: date | None, today: date) -> int | None:
    return (deadline - today).days if deadline else None


def _is_overdue_follow_up(opportunity: Any, today: date) -> bool:
    follow_up_date = getattr(opportunity, "follow_up_date", None)
    return bool(
        follow_up_date
        and follow_up_date <= today
        and getattr(opportunity, "stage", None) not in {"Won", "Lost"}
    )


def _top_priority(
    *,
    intelligence: Any,
    generation_job: Any,
    eligibility: Any,
    top_category: Any,
    prospects: list[Any],
    opportunities: list[Any],
    overdue_follow_ups: list[Any],
    outreach_waiting: list[Any],
) -> DashboardPriority:
    job_status = (
        (getattr(generation_job, "status", "") or "").lower()
        if generation_job is not None
        else ""
    )

    if job_status == "failed":
        return DashboardPriority(
            title="Strategy needs attention",
            message="The strategy could not be completed safely.",
            level="warning",
            action=DashboardAction(
                "Try again",
                "generate_workspace_sponsorship_intelligence",
                "POST",
            ),
            supporting_line=(
                getattr(generation_job, "message", None)
                or "Your existing intelligence was preserved."
            ),
        )

    if intelligence is not None and (
        eligibility is None
        or bool(getattr(eligibility, "research_blocked", True))
    ):
        missing = list(
            getattr(eligibility, "missing_information", []) or []
        )
        detail = (
            missing[0].replace("_", " ").capitalize()
            if missing
            else "Required sponsor eligibility information is incomplete."
        )
        return DashboardPriority(
            title="Resolve required information",
            message="Sponsor research is waiting for required information.",
            level="warning",
            action=DashboardAction("Edit setup", "setup"),
            supporting_line=detail,
        )

    if overdue_follow_ups:
        opportunity = overdue_follow_ups[0]
        return DashboardPriority(
            title="Follow-up due",
            message="A sponsor follow-up needs your attention today.",
            level="warning",
            action=DashboardAction(
                "Open follow-up",
                "opportunity_detail",
                route_params={"opportunity_id": opportunity.id},
            ),
            supporting_line=(
                getattr(opportunity, "recommended_target", None)
                or getattr(opportunity, "parent_prospect", None)
            ),
        )

    if outreach_waiting:
        opportunity = outreach_waiting[0]
        return DashboardPriority(
            title="Approve sponsor outreach",
            message="An outreach message is ready for your review.",
            level="primary",
            action=DashboardAction(
                "Review outreach",
                "opportunity_detail",
                route_params={"opportunity_id": opportunity.id},
            ),
            supporting_line=(
                getattr(opportunity, "recommended_target", None)
                or getattr(opportunity, "parent_prospect", None)
            ),
        )

    if intelligence is None:
        if job_status in ACTIVE_JOB_STATUSES:
            return DashboardPriority(
                title="Strategy work is underway",
                message=(
                    "Your Strategy Worker is preparing the sponsorship plan."
                ),
                level="info",
                action=DashboardAction(),
            )
        return DashboardPriority(
            title="Create your sponsorship strategy",
            message=(
                "Generate sponsorship intelligence before researching "
                "potential sponsors."
            ),
            level="primary",
            action=DashboardAction(
                "Start strategy work",
                "generate_workspace_sponsorship_intelligence",
                "POST",
            ),
        )

    if not prospects and top_category is not None:
        return DashboardPriority(
            title="Sponsor research is ready",
            message=(
                f"Begin with the highest-priority category: "
                f"{getattr(top_category, 'category', 'recommended sponsors')}."
            ),
            level="primary",
            action=DashboardAction(
                "Research sponsors",
                "prospects",
                "POST",
                {"category": top_category.slug},
            ),
        )

    if opportunities:
        return DashboardPriority(
            title="Review your active pipeline",
            message=(
                "Keep opportunities moving and confirm the next action for "
                "each sponsor."
            ),
            level="primary",
            action=DashboardAction("Open pipeline", "show_pipeline"),
        )

    return DashboardPriority(
        title="No action required",
        message="Your AI team is ready when you are.",
        level="success",
        action=DashboardAction(),
    )


def build_dashboard(
    *,
    organization: Any,
    initiative: Any,
    intelligence: Any = None,
    generation_job: Any = None,
    top_category: Any = None,
    prospects: Iterable[Any] = (),
    opportunities: Iterable[Any] = (),
    now: datetime | None = None,
) -> DashboardView:
    """Build the Release 1 dashboard without mutating application records."""

    current = now or datetime.now().astimezone()
    today = current.date()
    prospect_list = list(prospects)
    opportunity_list = list(opportunities)
    eligibility = (
        getattr(intelligence, "sponsor_eligibility", None)
        if intelligence is not None
        else None
    )
    overdue_follow_ups = [
        opportunity
        for opportunity in opportunity_list
        if _is_overdue_follow_up(opportunity, today)
    ]
    outreach_waiting = [
        opportunity
        for opportunity in opportunity_list
        if getattr(opportunity, "stage", None) == "Ready to Send"
    ]
    sponsors_secured = sum(
        getattr(opportunity, "stage", None) == "Won"
        for opportunity in opportunity_list
    )
    active_outreach = any(
        getattr(opportunity, "stage", None) in OUTREACH_ACTIVE_STAGES
        for opportunity in opportunity_list
    )
    job_status = (
        (getattr(generation_job, "status", "") or "").lower()
        if generation_job is not None
        else ""
    )
    research_blocked = bool(
        intelligence is not None
        and (
            eligibility is None
            or getattr(eligibility, "research_blocked", True)
        )
    )

    progress = (
        DashboardProgressStep("Organization Setup", "Complete"),
        DashboardProgressStep(
            "Strategy Meeting",
            (
                "Complete"
                if intelligence is not None
                else "Current"
                if job_status in ACTIVE_JOB_STATUSES
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Sponsor Research",
            (
                "Complete"
                if prospect_list
                else "Action required"
                if research_blocked
                else "Current"
                if intelligence is not None
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Outreach",
            (
                "Current"
                if opportunity_list
                else "Waiting"
                if prospect_list
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Follow-ups",
            (
                "Action required"
                if overdue_follow_ups
                else "Current"
                if active_outreach
                else "Waiting"
                if opportunity_list
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Sponsors Secured",
            "Complete" if sponsors_secured else "Not started",
        ),
    )

    if job_status == "failed":
        strategy_worker = DashboardWorker(
            "Strategy Worker",
            "Action required",
            "I couldn't complete the strategy safely.",
            DashboardAction(
                "Try again",
                "generate_workspace_sponsorship_intelligence",
                "POST",
            ),
            "Current task",
            "Retry strategy generation",
        )
    elif job_status in ACTIVE_JOB_STATUSES:
        strategy_worker = DashboardWorker(
            "Strategy Worker",
            "Working",
            "I'm building your sponsorship strategy now.",
            DashboardAction(),
            "Current task",
            "Analyze the active initiative",
        )
    elif intelligence is not None:
        strategy_worker = DashboardWorker(
            "Strategy Worker",
            "Complete",
            "I've completed your sponsorship strategy.",
            DashboardAction(
                "Regenerate",
                "generate_workspace_sponsorship_intelligence",
                "POST",
                {},
                {"regenerate": "true"},
            ),
            "Current task",
            "Ready for sponsor research",
        )
    else:
        strategy_worker = DashboardWorker(
            "Strategy Worker",
            "Ready",
            (
                "I've reviewed your setup and I'm ready to begin your "
                "sponsorship strategy."
            ),
            DashboardAction(
                "Start strategy work",
                "generate_workspace_sponsorship_intelligence",
                "POST",
            ),
            "Waiting on",
            "Your approval to begin",
        )

    if research_blocked:
        research_worker = DashboardWorker(
            "Research Worker",
            "Blocked",
            "I'm waiting for the required eligibility information.",
            DashboardAction("Edit setup", "setup"),
            "Waiting on",
            "Updated organization or audience details",
        )
    elif prospect_list:
        category = getattr(prospect_list[0], "category_slug", None)
        research_worker = DashboardWorker(
            "Research Worker",
            "Complete",
            (
                f"I've found {len(prospect_list)} evidence-backed sponsor "
                "prospect(s)."
            ),
            (
                DashboardAction(
                    "Review prospects",
                    "prospects",
                    route_params={"category": category},
                )
                if category
                else DashboardAction()
            ),
            "Current task",
            "Prospects ready for review",
        )
    elif intelligence is not None and top_category is not None:
        research_worker = DashboardWorker(
            "Research Worker",
            "Ready",
            "I'm ready to research your highest-priority sponsor category.",
            DashboardAction(
                "Research sponsors",
                "prospects",
                "POST",
                {"category": top_category.slug},
            ),
            "Current task",
            f"Research {getattr(top_category, 'category', 'approved sponsors')}",
        )
    else:
        research_worker = DashboardWorker(
            "Research Worker",
            "Waiting",
            "I'm waiting for the approved strategy before I begin research.",
            DashboardAction(),
            "Waiting on",
            "Strategy and eligibility approval",
        )

    if outreach_waiting:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Waiting for you",
            (
                f"I've prepared {len(outreach_waiting)} outreach item(s) for "
                "your review."
            ),
            DashboardAction(
                "Review outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_waiting[0].id},
            ),
            "Waiting on",
            "Your approval",
        )
    elif active_outreach:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Monitoring",
            (
                f"I'm managing {len(opportunity_list)} active outreach "
                "opportunit{'y' if len(opportunity_list) == 1 else 'ies'}."
            ),
            DashboardAction("Open pipeline", "show_pipeline"),
            "Current task",
            "Monitor responses and next actions",
        )
    else:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Waiting",
            "I'm waiting for an approved sponsor before I prepare outreach.",
            DashboardAction("Open pipeline", "show_pipeline"),
            "Waiting on",
            "An approved sponsor opportunity",
        )

    if overdue_follow_ups:
        pipeline_worker = DashboardWorker(
            "Pipeline Worker",
            "Action required",
            (
                f"I'm tracking {len(overdue_follow_ups)} follow-up(s) that "
                "need your attention."
            ),
            DashboardAction(
                "Open follow-up",
                "opportunity_detail",
                route_params={"opportunity_id": overdue_follow_ups[0].id},
            ),
            "Current task",
            "Keep sponsor conversations moving",
        )
    elif opportunity_list:
        pipeline_worker = DashboardWorker(
            "Pipeline Worker",
            "Monitoring",
            (
                f"I'm monitoring {len(opportunity_list)} active pipeline "
                f"opportunit{'y' if len(opportunity_list) == 1 else 'ies'}."
            ),
            DashboardAction("Open pipeline", "show_pipeline"),
            "Current task",
            f"{sponsors_secured} sponsor(s) secured",
        )
    else:
        pipeline_worker = DashboardWorker(
            "Pipeline Worker",
            "Ready",
            "I'm ready to track each approved sponsor opportunity.",
            DashboardAction("Open pipeline", "show_pipeline"),
            "Waiting on",
            "The first approved prospect",
        )

    return DashboardView(
        greeting=_greeting(current.hour, getattr(organization, "sender_name", None)),
        days_remaining=_days_remaining(
            getattr(initiative, "deadline", None),
            today,
        ),
        top_priority=_top_priority(
            intelligence=intelligence,
            generation_job=generation_job,
            eligibility=eligibility,
            top_category=top_category,
            prospects=prospect_list,
            opportunities=opportunity_list,
            overdue_follow_ups=overdue_follow_ups,
            outreach_waiting=outreach_waiting,
        ),
        progress=progress,
        workers=(
            strategy_worker,
            research_worker,
            outreach_worker,
            pipeline_worker,
        ),
        recent_activity=_build_recent_activity(
            intelligence,
            generation_job,
            prospect_list,
            opportunity_list,
        ),
        pipeline_count=len(opportunity_list),
        sponsors_secured=sponsors_secured,
    )

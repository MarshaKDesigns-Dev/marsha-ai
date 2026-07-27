"""Deterministic, read-only status building for the Coordinator dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Iterable

from services.sponsor_research_readiness import (
    strategy_meeting_is_complete,
)

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
    worker_name: str = "Pipeline Worker"
    worker_icon: str = "pipeline"
    status: str = "Ready"


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
    next_title: str
    next_message: str
    progress: tuple[DashboardProgressStep, ...]
    workers: tuple[DashboardWorker, ...]
    recent_activity: tuple[DashboardActivity, ...]
    pipeline_count: int
    sponsors_secured: int
    approved_asset_count: int
    prospect_count: int
    job_status: str


def _first_name(sender_name: str | None) -> str:
    value = (sender_name or "").strip()
    return value.split()[0] if value else "there"


def _greeting(hour: int, sender_name: str | None) -> str:
    if not (sender_name or "").strip():
        return "Welcome back"
    if hour < 12:
        salutation = "Good morning"
    elif hour < 18:
        salutation = "Good afternoon"
    else:
        salutation = "Good evening"
    return f"{salutation}, {_first_name(sender_name)}"


def _whats_next(priority: DashboardPriority) -> tuple[str, str]:
    """Explain the stage that follows the current required action."""

    return {
        "Complete your sponsorship setup": (
            "Meet with your Strategy Worker",
            "After setup, the Strategy Worker can prepare your sponsorship plan.",
        ),
        "Your Strategy Worker is ready": (
            "Generate your sponsorship strategy",
            "Complete the Strategy Meeting to provide campaign priorities and constraints.",
        ),
        "Your Strategy Worker is preparing your sponsorship strategy": (
            "Review Sponsorship Assets",
            "When strategy work finishes, approve the opportunities you can deliver.",
        ),
        "Your sponsorship strategy is ready for review": (
            "Assign sponsor research",
            "After approving an asset, choose what the Research Worker should research.",
        ),
        "Your Research Worker is searching for sponsors": (
            "Review Research Results",
            "When research finishes, choose which qualified sponsors to save.",
        ),
        "Your sponsor research is ready for review": (
            "Build your pipeline",
            "Save the qualified sponsor opportunities you want to pursue.",
        ),
        "What would you like your Research Worker to research next?": (
            "Review qualified sponsors",
            "Assign one approved sponsorship asset at a time.",
        ),
        "Your Outreach Worker is ready": (
            "Review sponsor communication",
            "Create a tailored message for the selected opportunity.",
        ),
        "Your Outreach Worker is preparing sponsor communication": (
            "Approve sponsor communication",
            "Review the tailored message before delivery.",
        ),
        "Manage your sponsorship pipeline": (
            "Keep sponsor conversations moving",
            "Review delivery status, next actions, and follow-up dates.",
        ),
        "Strategy needs attention": (
            "Strategy generation resumes",
            "After a successful retry, you will review the generated sponsorship assets.",
        ),
        "Strategy work is underway": (
            "Review Sponsorship Assets",
            "When the Strategy Worker finishes, approve the benefits you can deliver.",
        ),
        "Resolve required information": (
            "Generate your sponsorship strategy",
            "After the missing information is resolved, the Strategy Worker can build the plan.",
        ),
        "Follow-up due": (
            "Update the sponsor pipeline",
            "After following up, record the response and next commitment.",
        ),
        "Approve sponsor outreach": (
            "Contact the sponsor",
            "After approval, use the verified delivery route and track the response.",
        ),
        "Review Sponsorship Assets.": (
            "Research aligned sponsors",
            "After at least one asset is approved, the Research Worker can find prospects.",
        ),
        "Create your sponsorship strategy": (
            "Review Sponsorship Assets",
            "After generation, confirm which recommended benefits you can deliver.",
        ),
        "Sponsor research is ready": (
            "Review Sponsor Opportunities",
            "After research, choose the evidence-backed sponsors you want to pursue.",
        ),
        "Review Sponsor Opportunities": (
            "Prepare sponsor outreach",
            "After approving a prospect, create an opportunity and review its outreach.",
        ),
        "Review your active pipeline": (
            "Keep sponsor conversations moving",
            "Record responses, commitments, and follow-up dates for each opportunity.",
        ),
    }.get(
        priority.title,
        (
            "Monitor your active pipeline",
            "Your AI team will surface the next action when one becomes available.",
        ),
    )


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
    organization: Any,
    initiative: Any,
    intelligence: Any,
    generation_job: Any,
    eligibility: Any,
    top_category: Any,
    meeting_complete: bool,
    approved_asset_count: int,
    assignments: list[Any],
    prospects: list[Any],
    opportunities: list[Any],
    overdue_follow_ups: list[Any],
    outreach_waiting: list[Any],
) -> DashboardPriority:
    """Select one internally consistent hero from persisted workflow state."""

    def hero(
        worker_name,
        worker_icon,
        status,
        title,
        message,
        action,
        *,
        level="primary",
        supporting_line=None,
    ):
        return DashboardPriority(
            title=title,
            message=message,
            level=level,
            action=action,
            supporting_line=supporting_line,
            worker_name=worker_name,
            worker_icon=worker_icon,
            status=status,
        )

    job_status = (
        (getattr(generation_job, "status", "") or "").lower()
        if generation_job is not None
        else ""
    )

    setup_complete = bool(
        organization
        and initiative
        and (getattr(organization, "name", "") or "").strip()
        and (getattr(initiative, "name", "") or "").strip()
    )
    if not setup_complete:
        return hero(
            "Organization Setup",
            "organization",
            "Action Required",
            "Complete your sponsorship setup",
            (
                "Provide the organization and initiative information Marsha "
                "AI needs before the Strategy Worker can begin."
            ),
            DashboardAction("Continue Setup", "setup"),
        )

    if job_status == "failed":
        return hero(
            "Strategy Worker",
            "strategy",
            "Needs Attention",
            "Your Strategy Worker needs attention",
            "Strategy generation stopped before completion.",
            DashboardAction(
                "Retry Strategy Generation",
                "generate_workspace_sponsorship_intelligence",
                "POST",
                form_data=(
                    {"regenerate": "true"}
                    if intelligence is not None
                    else {}
                ),
            ),
            level="warning",
            supporting_line=(
                getattr(generation_job, "message", None)
                or "Your existing intelligence was preserved."
            ),
        )

    if job_status in ACTIVE_JOB_STATUSES:
        return hero(
            "Strategy Worker",
            "strategy",
            "Working",
            "Your Strategy Worker is preparing your sponsorship strategy",
            (
                "I’m reviewing your organization, initiative, priorities, "
                "goals, and constraints."
            ),
            DashboardAction(),
            level="info",
        )

    if not meeting_complete or intelligence is None:
        return hero(
            "Strategy Worker",
            "strategy",
            "Ready",
            "Your Strategy Worker is ready",
            (
                "Complete the Strategy Meeting so Marsha AI can prepare your "
                "sponsorship strategy and recommended assets."
            ),
            DashboardAction("Begin Strategy Meeting", "strategy_meeting"),
        )

    if approved_asset_count == 0:
        return hero(
            "Strategy Worker",
            "strategy",
            "Ready for Review",
            "Your sponsorship strategy is ready for review",
            (
                "Review the recommended sponsorship assets and approve the "
                "opportunities your organization can offer."
            ),
            DashboardAction(
                "Review Strategy",
                "strategy_work",
            ),
        )

    def assignment_is_reviewed(assignment):
        result_count = getattr(assignment, "result_count", 0) or 0
        if result_count == 0:
            return True
        completed_at = _as_utc(getattr(assignment, "completed_at", None))
        return any(
            (
                getattr(opportunity, "sponsorship_asset_id", None)
                == getattr(assignment, "sponsorship_asset_id", None)
            )
            and (
                completed_at is None
                or _as_utc(getattr(opportunity, "created_at", None)) is None
                or _as_utc(getattr(opportunity, "created_at", None))
                >= completed_at
            )
            for opportunity in opportunities
        )

    attention_assignment = next(
        (
            item
            for item in assignments
            if (getattr(item, "status", "") or "").lower()
            == "needs_attention"
        ),
        None,
    )
    working_assignment = next(
        (
            item
            for item in assignments
            if (getattr(item, "status", "") or "").lower() == "working"
        ),
        None,
    )
    review_assignment = next(
        (
            item
            for item in assignments
            if (getattr(item, "status", "") or "").lower() == "completed"
            and not assignment_is_reviewed(item)
        ),
        None,
    )

    if attention_assignment is not None:
        return hero(
            "Research Worker",
            "research",
            "Needs Attention",
            "Your Research Worker could not complete the assignment",
            (
                "Review the issue and retry the research assignment or choose "
                "another approved asset."
            ),
            DashboardAction(
                "Review Research Assignment",
                "research_assignment",
                route_params={"assignment_id": attention_assignment.id},
            ),
            level="warning",
        )
    if working_assignment is not None:
        return hero(
            "Research Worker",
            "research",
            "Working",
            "Your Research Worker is searching for sponsors",
            (
                "I’m analyzing organizations that match your selected "
                "sponsorship asset, strategy, geography, and sponsor criteria."
            ),
            DashboardAction(
                "View Research Progress",
                "research_assignment",
                route_params={"assignment_id": working_assignment.id},
            ),
            level="info",
            supporting_line=getattr(working_assignment, "asset_name", None),
        )

    if review_assignment is not None:
        return hero(
            "Research Worker",
            "research",
            "Completed",
            "Your sponsor research is ready for review",
            (
                "Review the qualified prospects and decide which "
                "organizations to save to your pipeline."
            ),
            DashboardAction(
                "Review Research Results",
                "research_assignment",
                route_params={"assignment_id": review_assignment.id},
            ),
        )

    if eligibility is None or bool(
        getattr(eligibility, "research_blocked", True)
    ):
        missing = list(
            getattr(eligibility, "missing_information", []) or []
        )
        detail = (
            missing[0].replace("_", " ").capitalize()
            if missing
            else "Required sponsor eligibility information is incomplete."
        )
        return hero(
            "Research Worker",
            "research",
            "Needs Attention",
            "Your Research Worker needs required information",
            "Sponsor research is waiting for required information.",
            DashboardAction("Edit Setup", "setup"),
            level="warning",
            supporting_line=detail,
        )

    outreach_working = next(
        (
            item
            for item in opportunities
            if (
                getattr(item, "stage", None)
                in {"Outreach Working", "Message Review"}
                or bool(getattr(item, "outreach", None))
                or bool(getattr(item, "reviewed_message", None))
                or bool(getattr(item, "message_reviewed_at", None))
            )
            and getattr(item, "stage", None) not in OUTREACH_ACTIVE_STAGES
        ),
        None,
    )
    outreach_ready = next(
        (
            item
            for item in opportunities
            if getattr(item, "stage", None) == "Ready to Send"
            and not getattr(item, "outreach", None)
            and not getattr(item, "reviewed_message", None)
            and not getattr(item, "message_reviewed_at", None)
        ),
        None,
    )
    if outreach_working is not None:
        return hero(
            "Outreach Worker",
            "outreach",
            "Working",
            "Your Outreach Worker is preparing sponsor communication",
            (
                "I’m creating a message tailored to the sponsor, sponsorship "
                "asset, and initiative."
            ),
            DashboardAction(
                "View Outreach Work",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_working.id},
            ),
            level="info",
        )
    if outreach_ready is not None:
        return hero(
            "Outreach Worker",
            "outreach",
            "Ready",
            "Your Outreach Worker is ready",
            (
                "Select a sponsor opportunity and create a tailored outreach "
                "message."
            ),
            DashboardAction(
                "Begin Outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_ready.id},
            ),
        )

    pipeline_opportunities = [
        item
        for item in opportunities
        if getattr(item, "stage", None) in OUTREACH_ACTIVE_STAGES
        or getattr(item, "follow_up_date", None)
        or getattr(item, "sent_date", None)
    ]
    if not pipeline_opportunities:
        return hero(
            "Research Worker",
            "research",
            "Ready",
            "What would you like your Research Worker to research next?",
            (
                "Choose one approved sponsorship asset and I’ll identify "
                "qualified sponsor prospects for that opportunity."
            ),
            DashboardAction("Assign Research", "research_worker"),
        )

    pipeline_target = overdue_follow_ups[0] if overdue_follow_ups else None
    return hero(
        "Pipeline Worker",
        "pipeline",
        "Action Required" if pipeline_target else "Monitoring",
        "Manage your sponsorship pipeline",
        (
            "Review saved opportunities, outreach status, next actions, and "
            "follow-up dates."
        ),
        (
            DashboardAction(
                "Open Follow-up",
                "opportunity_detail",
                route_params={"opportunity_id": pipeline_target.id},
            )
            if pipeline_target
            else DashboardAction("Open Pipeline", "show_pipeline")
        ),
        level="warning" if pipeline_target else "primary",
    )


def build_dashboard(
    *,
    organization: Any,
    initiative: Any,
    intelligence: Any = None,
    generation_job: Any = None,
    top_category: Any = None,
    assets: Iterable[Any] = (),
    prospects: Iterable[Any] = (),
    opportunities: Iterable[Any] = (),
    research_assignments: Iterable[Any] = (),
    now: datetime | None = None,
) -> DashboardView:
    """Build the Release 1 dashboard without mutating application records."""

    current = now or datetime.now().astimezone()
    today = current.date()
    prospect_list = list(prospects)
    asset_list = list(assets)
    opportunity_list = list(opportunities)
    assignment_list = list(research_assignments)
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
    meeting_complete = strategy_meeting_is_complete(
        initiative,
        intelligence,
    )
    approved_asset_count = sum(
        getattr(asset, "is_active", True)
        and getattr(asset, "approval_status", "Pending") == "Approved"
        for asset in asset_list
    )
    setup_complete = bool(
        organization
        and initiative
        and (getattr(organization, "name", "") or "").strip()
        and (getattr(initiative, "name", "") or "").strip()
    )
    strategy_ready = bool(meeting_complete and intelligence is not None)

    progress = (
        DashboardProgressStep(
            "Organization Setup",
            "Complete" if setup_complete else "Current",
        ),
        DashboardProgressStep(
            "Strategy Meeting",
            (
                "Complete"
                if strategy_ready
                else "Current"
                if setup_complete
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Sponsor Research",
            (
                "Complete"
                if strategy_ready and prospect_list
                else "Action required"
                if strategy_ready and (
                    research_blocked or (
                    intelligence is not None
                    and approved_asset_count == 0
                    )
                )
                else "Current"
                if strategy_ready
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Outreach",
            (
                "Current"
                if strategy_ready and opportunity_list
                else "Waiting"
                if strategy_ready and prospect_list
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Follow-ups",
            (
                "Action required"
                if strategy_ready and overdue_follow_ups
                else "Current"
                if strategy_ready and active_outreach
                else "Waiting"
                if strategy_ready and opportunity_list
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Sponsors Secured",
            "Complete"
            if strategy_ready and sponsors_secured
            else "Not started",
        ),
    )

    if job_status == "failed":
        strategy_worker = DashboardWorker(
            "Strategy Worker",
            "Action required",
            "I couldn't complete the strategy safely.",
            DashboardAction(
                "Retry Strategy Generation",
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
        if approved_asset_count == 0:
            strategy_worker = DashboardWorker(
                "Strategy Worker",
                "Ready for Review",
                "I've completed your sponsorship strategy.",
                DashboardAction("Review Strategy", "strategy_work"),
                "Waiting on",
                "Your strategy approval",
            )
        else:
            strategy_worker = DashboardWorker(
                "Strategy Worker",
                "Complete",
                "I've completed and applied your approved strategy.",
                DashboardAction("Review Strategy", "strategy_work"),
                "Current task",
                "Support the Research Worker",
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
                "Begin Strategy Meeting",
                "strategy_meeting",
            ),
            "Waiting on",
            "Your approval to begin",
        )

    if not strategy_ready:
        research_worker = DashboardWorker(
            "Research Worker",
            "Waiting",
            "I'm waiting for the approved strategy before I begin research.",
            DashboardAction(),
            "Waiting on",
            "Strategy and eligibility approval",
        )
    elif intelligence is not None and approved_asset_count == 0:
        research_worker = DashboardWorker(
            "Research Worker",
            "Waiting",
            "I'm waiting for strategy approval.",
            DashboardAction(
                "Review Strategy",
                "strategy_work",
            ),
            "Waiting on",
            "Your strategy approval",
        )
    elif research_blocked:
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
            DashboardAction("Open pipeline", "show_pipeline"),
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
                "research_worker",
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

    if not strategy_ready:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Waiting",
            "I'm waiting for approved sponsor research before outreach begins.",
            DashboardAction(),
            "Waiting on",
            "Strategy and sponsor research",
        )
    elif outreach_waiting:
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

    if not strategy_ready:
        pipeline_worker = DashboardWorker(
            "Pipeline Worker",
            "Waiting",
            "I'm waiting for the sponsorship workflow to reach the pipeline.",
            DashboardAction(),
            "Waiting on",
            "Strategy, research, and outreach",
        )
    elif overdue_follow_ups:
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

    top_priority = _top_priority(
        organization=organization,
        initiative=initiative,
        intelligence=intelligence,
        generation_job=generation_job,
        eligibility=eligibility,
        top_category=top_category,
        meeting_complete=meeting_complete,
        approved_asset_count=approved_asset_count,
        assignments=assignment_list,
        prospects=prospect_list,
        opportunities=opportunity_list,
        overdue_follow_ups=overdue_follow_ups,
        outreach_waiting=outreach_waiting,
    )
    next_title, next_message = _whats_next(top_priority)
    workers = [
        strategy_worker,
        research_worker,
        outreach_worker,
        pipeline_worker,
    ]
    for index, worker in enumerate(workers):
        if worker.name == top_priority.worker_name:
            workers[index] = DashboardWorker(
                name=top_priority.worker_name,
                status=top_priority.status,
                message=top_priority.message,
                action=top_priority.action,
                detail_label="Current stage",
                detail=top_priority.title,
            )
            break

    return DashboardView(
        greeting=_greeting(current.hour, getattr(organization, "sender_name", None)),
        days_remaining=_days_remaining(
            getattr(initiative, "deadline", None),
            today,
        ),
        top_priority=top_priority,
        next_title=next_title,
        next_message=next_message,
        progress=progress,
        workers=tuple(workers),
        recent_activity=_build_recent_activity(
            intelligence,
            generation_job,
            prospect_list,
            opportunity_list,
        ),
        pipeline_count=len(opportunity_list),
        sponsors_secured=sponsors_secured,
        approved_asset_count=approved_asset_count,
        prospect_count=len(prospect_list),
        job_status=job_status,
    )

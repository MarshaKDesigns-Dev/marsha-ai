"""Deterministic, read-only status building for the Coordinator dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Iterable

from services.sponsor_research_readiness import (
    strategy_meeting_is_complete,
)
from services.workflow_navigation import build_primary_navigation

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
class DashboardMetric:
    """One reliable, context-sensitive sponsorship metric."""

    label: str
    value: int


@dataclass(frozen=True)
class DashboardAttention:
    """One actionable item ordered by workflow urgency."""

    title: str
    context: str
    action: DashboardAction
    urgency: int


@dataclass(frozen=True)
class DashboardLink:
    """A subdued destination for revisiting available work."""

    label: str
    endpoint: str


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
    current_stage: str = "Organization Setup"
    workflow_progress: tuple[Any, ...] = ()
    ai_team: tuple[DashboardWorker, ...] = ()
    metrics: tuple[DashboardMetric, ...] = ()
    needs_attention: tuple[DashboardAttention, ...] = ()
    continue_links: tuple[DashboardLink, ...] = ()


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
            "Complete Sponsorship Strategy to provide priorities and constraints.",
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
            "Review Sponsor Research",
            "When research finishes, choose which qualified sponsors to save.",
        ),
        "Your sponsor research is ready for review": (
            "Build your Sponsor Pipeline",
            "Save the qualified sponsor opportunities you want to pursue.",
        ),
        "What would you like your Research Worker to research next?": (
            "Review Sponsor Research",
            "Assign one approved sponsorship asset at a time.",
        ),
        "Your Outreach Worker is ready": (
            "Review Outreach",
            "Create tailored Sponsor Outreach for the selected opportunity.",
        ),
        "Your Outreach Worker is preparing Sponsor Outreach": (
            "Approve Outreach",
            "Review the final outreach before sending.",
        ),
        "Manage your Sponsor Pipeline": (
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
            "Update the Sponsor Pipeline",
            "After following up, record the response and next commitment.",
        ),
        "Approve Outreach": (
            "Contact the sponsor",
            "After approval, use the verified delivery route and track the response.",
        ),
        "Review Sponsorship Assets.": (
            "Research aligned sponsors",
            "After at least one asset is approved, the Research Worker can find sponsors.",
        ),
        "Create your sponsorship strategy": (
            "Review Sponsorship Assets",
            "After generation, confirm which recommended benefits you can deliver.",
        ),
        "Sponsor research is ready": (
            "Review Sponsor Research",
            "After research, choose the evidence-backed sponsors you want to pursue.",
        ),
        "Review Sponsor Research": (
            "Generate Outreach",
            "After approving a sponsor, create a Sponsor Opportunity and review its outreach.",
        ),
        "Review your Sponsor Pipeline": (
            "Keep sponsor conversations moving",
            "Record responses, commitments, and follow-up dates for each opportunity.",
        ),
    }.get(
        priority.title,
        (
            "Monitor your Sponsor Pipeline",
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
            or "A sponsor organization"
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
        and not getattr(opportunity, "follow_up_completed_at", None)
    )


def _waiting_key(record: Any) -> tuple[float, int]:
    """Order equal-priority records by oldest persisted wait, then ID."""

    timestamp = _as_utc(
        getattr(record, "created_at", None)
        or getattr(record, "updated_at", None)
        or getattr(record, "started_at", None)
    )
    return (
        timestamp.timestamp() if timestamp is not None else float("inf"),
        getattr(record, "id", 0) or 0,
    )


def _follow_up_key(record: Any) -> tuple[date, float, int]:
    return (
        getattr(record, "follow_up_date", None) or date.max,
        *_waiting_key(record),
    )


def _latest_assignments_by_asset(assignments: Iterable[Any]) -> list[Any]:
    """Return only the newest persisted attempt for each research asset."""

    latest: dict[Any, Any] = {}
    for assignment in assignments:
        asset_id = getattr(assignment, "sponsorship_asset_id", None)
        existing = latest.get(asset_id)
        if existing is None:
            latest[asset_id] = assignment
            continue
        assignment_time = _as_utc(getattr(assignment, "created_at", None))
        existing_time = _as_utc(getattr(existing, "created_at", None))
        assignment_key = (
            assignment_time.timestamp() if assignment_time else float("-inf"),
            getattr(assignment, "id", 0) or 0,
        )
        existing_key = (
            existing_time.timestamp() if existing_time else float("-inf"),
            getattr(existing, "id", 0) or 0,
        )
        if assignment_key > existing_key:
            latest[asset_id] = assignment
    return list(latest.values())


def _has_usable_contact(opportunity: Any) -> bool:
    return any(
        (
            getattr(opportunity, "email", None),
            getattr(opportunity, "phone", None),
            getattr(opportunity, "contact_url", None),
        )
    )


def _outreach_is_available(opportunity: Any) -> bool:
    return bool(
        getattr(opportunity, "stage", None) == "Research Approved"
        and _has_usable_contact(opportunity)
        and not getattr(opportunity, "outreach", None)
        and not getattr(opportunity, "reviewed_message", None)
    )


def _mission_control_metrics(
    *,
    strategy_approved: bool,
    research_started: bool,
    approved_asset_count: int,
    prospect_count: int,
    opportunities: list[Any],
    overdue_follow_ups: list[Any],
) -> tuple[DashboardMetric, ...]:
    if not strategy_approved:
        return ()

    metrics = [DashboardMetric("Approved Assets", approved_asset_count)]
    if research_started or prospect_count or opportunities:
        metrics.extend(
            (
                DashboardMetric("Sponsors Researched", prospect_count),
                DashboardMetric("Sponsors in Pipeline", len(opportunities)),
            )
        )
    if opportunities:
        metrics.extend(
            (
                DashboardMetric(
                    "Outreach Ready",
                    sum(
                        getattr(item, "stage", None) == "Ready to Send"
                        and bool(getattr(item, "message_approved_at", None))
                        for item in opportunities
                    ),
                ),
                DashboardMetric(
                    "Outreach Sent",
                    sum(
                        bool(getattr(item, "sent_date", None))
                        or getattr(item, "stage", None)
                        in {
                            "Sent",
                            "Follow-Up Due",
                            "Responded",
                            "Meeting",
                            "Proposal",
                            "Won",
                            "Lost",
                        }
                        for item in opportunities
                    ),
                ),
                DashboardMetric("Follow-Ups Due", len(overdue_follow_ups)),
            )
        )
    return tuple(metrics)


def _mission_control_attention(
    *,
    intelligence: Any,
    generation_job: Any,
    approved_asset_count: int,
    assignments: list[Any],
    opportunities: list[Any],
    overdue_follow_ups: list[Any],
    top_priority: DashboardPriority,
) -> tuple[DashboardAttention, ...]:
    items: list[DashboardAttention] = []
    top_endpoint = top_priority.action.endpoint
    job_status = (
        (getattr(generation_job, "status", "") or "").lower()
        if generation_job is not None
        else ""
    )
    if job_status == "failed":
        items.append(
            DashboardAttention(
                "Strategy generation needs attention",
                getattr(generation_job, "message", None)
                or "The Strategy Worker could not finish safely.",
                DashboardAction(
                    "Retry Strategy Generation",
                    "generate_workspace_sponsorship_intelligence",
                    "POST",
                ),
                1,
            )
        )
    if intelligence is not None and approved_asset_count == 0:
        items.append(
            DashboardAttention(
                "Sponsorship Strategy needs approval",
                "Review the recommended sponsorship assets.",
                DashboardAction("Continue Strategy Review", "strategy_work"),
                3,
            )
        )
    for assignment in _latest_assignments_by_asset(assignments):
        status = (getattr(assignment, "status", "") or "").lower()
        if status == "needs_attention":
            items.append(
                DashboardAttention(
                    "Sponsor Research needs attention",
                    getattr(assignment, "asset_name", None)
                    or "A research assignment could not be completed.",
                    DashboardAction(
                        "Retry Sponsor Research",
                        "research_assignment",
                        route_params={"assignment_id": assignment.id},
                    ),
                    1,
                )
            )
        elif (
            status == "completed"
            and (getattr(assignment, "result_count", 0) or 0)
            and not any(
                getattr(opportunity, "sponsorship_asset_id", None)
                == getattr(assignment, "sponsorship_asset_id", None)
                for opportunity in opportunities
            )
        ):
            items.append(
                DashboardAttention(
                    "Sponsor Research is ready for review",
                    getattr(assignment, "asset_name", None)
                    or "Qualified sponsors are waiting for your decision.",
                    DashboardAction(
                        "Review Sponsor Results",
                        "research_assignment",
                        route_params={"assignment_id": assignment.id},
                    ),
                    5,
                )
            )
    due_ids = {getattr(item, "id", None) for item in overdue_follow_ups}
    for opportunity in opportunities:
        target = (
            getattr(opportunity, "recommended_target", None)
            or getattr(opportunity, "parent_prospect", None)
            or "Sponsor Opportunity"
        )
        action = DashboardAction(
            "Open Sponsor Opportunity",
            "opportunity_detail",
            route_params={"opportunity_id": opportunity.id},
        )
        if getattr(opportunity, "id", None) in due_ids:
            items.append(
                DashboardAttention(
                    "Follow-Up Due", target,
                    DashboardAction(
                        "Continue Follow-Up", "opportunity_detail",
                        route_params={"opportunity_id": opportunity.id},
                    ), 2,
                )
            )
        elif getattr(opportunity, "stage", None) == "Ready to Send":
            if not getattr(opportunity, "message_reviewed_at", None):
                items.append(
                    DashboardAttention(
                        "Outreach Review required",
                        target,
                        DashboardAction(
                            "Continue Outreach Review", "opportunity_detail",
                            route_params={"opportunity_id": opportunity.id},
                        ),
                        3,
                    )
                )
            elif not getattr(opportunity, "message_approved_at", None):
                items.append(
                    DashboardAttention(
                        "Outreach approval required",
                        target,
                        DashboardAction(
                            "Approve Outreach", "opportunity_detail",
                            route_params={"opportunity_id": opportunity.id},
                        ),
                        3,
                    )
                )
            else:
                items.append(
                    DashboardAttention(
                        "Outreach is ready to send",
                        target,
                        DashboardAction(
                            "Send Outreach", "opportunity_detail",
                            route_params={"opportunity_id": opportunity.id},
                        ),
                        4,
                    )
                )

    ordered = sorted(
        items,
        key=lambda item: (
            item.urgency,
            item.action.route_params.get("opportunity_id", float("inf")),
            item.action.route_params.get("assignment_id", float("inf")),
        ),
    )
    if top_endpoint:
        ordered = [
            item
            for item in ordered
            if not (
                item.action.endpoint == top_endpoint
                and item.action.route_params
                == top_priority.action.route_params
            )
        ]
    return tuple(ordered[:5])


def _mission_control_activity(
    *,
    intelligence: Any,
    generation_job: Any,
    assets: list[Any],
    prospects: list[Any],
    assignments: list[Any],
    opportunities: list[Any],
) -> tuple[DashboardActivity, ...]:
    items: list[DashboardActivity] = []

    def add(message: str, timestamp: datetime | None, action=None):
        occurred_at = _as_utc(timestamp)
        if occurred_at is not None:
            items.append(DashboardActivity(message, occurred_at, action))

    if generation_job is not None and (
        (getattr(generation_job, "status", "") or "").lower() == "completed"
    ):
        add(
            "Sponsorship strategy generated",
            getattr(generation_job, "completed_at", None)
            or getattr(generation_job, "updated_at", None),
        )
    elif intelligence is not None:
        add(
            "Sponsorship strategy generated",
            getattr(intelligence, "generated_at", None)
            or getattr(intelligence, "created_at", None),
        )
    for asset in assets:
        if getattr(asset, "approval_status", None) == "Approved":
            add(
                f"{getattr(asset, 'name', 'Sponsorship asset')} approved",
                getattr(asset, "approval_updated_at", None),
                DashboardAction("View Strategy", "strategy_work"),
            )
    for assignment in assignments:
        if (getattr(assignment, "status", "") or "").lower() == "completed":
            add(
                "Sponsor Research completed",
                getattr(assignment, "completed_at", None),
                DashboardAction(
                    "Review research",
                    "research_assignment",
                    route_params={"assignment_id": assignment.id},
                ),
            )
    for prospect in prospects:
        add(
            f"{getattr(prospect, 'company_name', 'Sponsor')} researched",
            getattr(prospect, "created_at", None),
        )
    for opportunity in opportunities:
        target = (
            getattr(opportunity, "recommended_target", None)
            or getattr(opportunity, "parent_prospect", None)
            or "Sponsor"
        )
        action = DashboardAction(
            "Open opportunity",
            "opportunity_detail",
            route_params={"opportunity_id": opportunity.id},
        )
        add(
            f"{target} added to Sponsor Pipeline",
            getattr(opportunity, "created_at", None),
            action,
        )
        add(
            f"Outreach for {target} reviewed",
            getattr(opportunity, "message_reviewed_at", None),
            action,
        )
        add(
            f"Outreach for {target} approved",
            getattr(opportunity, "message_approved_at", None),
            action,
        )
        sent_date = getattr(opportunity, "sent_date", None)
        if sent_date is not None:
            add(
                f"Outreach to {target} sent",
                datetime.combine(sent_date, datetime.min.time(), tzinfo=UTC),
                action,
            )
        add(
            f"Follow-Up with {target} sent",
            getattr(opportunity, "follow_up_completed_at", None),
            action,
        )
    return tuple(
        sorted(items, key=lambda item: item.occurred_at, reverse=True)[:5]
    )


def _mission_control_team(
    *,
    strategy_worker: DashboardWorker,
    research_worker: DashboardWorker,
    outreach_worker: DashboardWorker,
    strategy_ready: bool,
    opportunities: list[Any],
    overdue_follow_ups: list[Any],
) -> tuple[DashboardWorker, ...]:
    review_waiting = [
        item
        for item in opportunities
        if getattr(item, "stage", None) == "Ready to Send"
        and bool(
            getattr(item, "outreach", None)
            or getattr(item, "reviewed_message", None)
        )
        and not getattr(item, "message_reviewed_at", None)
    ]
    review_worker = DashboardWorker(
        "Message Quality Review Worker",
        "Needs Attention" if review_waiting else "Complete" if opportunities else "Waiting",
        (
            f"{len(review_waiting)} outreach draft(s) waiting for review."
            if review_waiting
            else "No outreach drafts are waiting for review."
            if opportunities
            else "Sponsor Outreach must be prepared first."
        ),
        DashboardAction(),
    )
    follow_up_worker = DashboardWorker(
        "Follow-Up Worker",
        "Ready" if overdue_follow_ups else "Waiting",
        (
            f"{len(overdue_follow_ups)} sponsor follow-up(s) are due."
            if overdue_follow_ups
            else "No sponsor follow-ups are due."
        ),
        DashboardAction(),
    )

    normalized = []
    for worker in (
        strategy_worker,
        research_worker,
        outreach_worker,
        review_worker,
        follow_up_worker,
    ):
        status = worker.status
        if status in {"Ready for Review", "Waiting for you", "Monitoring", "Blocked", "Action required"}:
            status = {
                "Ready for Review": "Ready",
                "Waiting for you": "Needs Attention",
                "Monitoring": "Working",
                "Blocked": "Needs Attention",
                "Action required": "Needs Attention",
            }[status]
        normalized.append(
            DashboardWorker(
                worker.name,
                status,
                worker.message,
                DashboardAction(),
                worker.detail_label,
                worker.detail,
            )
        )
    if not strategy_ready:
        return tuple(normalized[:2])
    if not opportunities:
        return tuple(normalized[:3])
    return tuple(normalized)


def _legacy_top_priority(
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
                "Complete Sponsorship Strategy so Marsha AI can prepare your "
                "sponsorship strategy and recommended assets."
            ),
            DashboardAction("Build Sponsorship Strategy", "strategy_meeting"),
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
                "View Strategy",
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
            if (getattr(item, "status", "") or "").lower()
            in {"ready", "working"}
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
                "Review the qualified sponsors and decide which "
                "organizations to save to your Sponsor Pipeline."
            ),
            DashboardAction(
                "Review Sponsor Research",
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

    outreach_review = next(
        (
            item
            for item in outreach_waiting
            if not getattr(item, "message_reviewed_at", None)
        ),
        None,
    )
    outreach_approval = next(
        (
            item
            for item in outreach_waiting
            if getattr(item, "message_reviewed_at", None)
            and not getattr(item, "message_approved_at", None)
        ),
        None,
    )
    outreach_send = next(
        (
            item
            for item in outreach_waiting
            if getattr(item, "message_approved_at", None)
        ),
        None,
    )
    outreach_working = next(
        (
            item
            for item in opportunities
            if (
                getattr(
                    getattr(item, "outreach_generation_job", None),
                    "status", None,
                ) in {"queued", "working"}
                or
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
    if outreach_review is not None:
        return hero(
            "Outreach Worker",
            "outreach",
            "Waiting for you",
            "Review the prepared sponsor outreach",
            "The generated outreach is ready for Outreach Review.",
            DashboardAction(
                "Review outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_review.id},
            ),
        )
    if outreach_approval is not None:
        return hero(
            "Outreach Worker",
            "outreach",
            "Waiting for you",
            "Approve the reviewed sponsor outreach",
            "The reviewed message needs your explicit approval before sending.",
            DashboardAction(
                "Approve outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_approval.id},
            ),
        )
    if outreach_send is not None:
        return hero(
            "Outreach Worker",
            "outreach",
            "Ready",
            "Send the approved sponsor outreach",
            "The reviewed message is approved and ready for delivery.",
            DashboardAction(
                "Send outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_send.id},
            ),
        )
    if outreach_working is not None:
        return hero(
            "Outreach Worker",
            "outreach",
            "Working",
            "Your Outreach Worker is preparing Sponsor Outreach",
            (
                "I’m creating a message tailored to the sponsor, sponsorship "
                "asset, and initiative."
            ),
            DashboardAction(
                "View Outreach Preparation",
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
                "Generate Outreach",
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
                "qualified sponsor organizations for that opportunity."
            ),
            DashboardAction("Assign Research", "research_worker"),
        )

    active_follow_up = next(
        (
            item for item in opportunities
            if getattr(
                getattr(item, "follow_up_generation_job", None),
                "status", None,
            ) in {"queued", "working"}
        ),
        None,
    )
    if active_follow_up is not None:
        return hero(
            "Follow-Up Worker", "pipeline", "Working",
            "Your Follow-Up Worker is preparing the follow-up",
            "I’m using the original outreach, delivery history, and scheduled follow-up.",
            DashboardAction(
                "View Follow-Up Progress", "opportunity_detail",
                route_params={"opportunity_id": active_follow_up.id},
            ), level="info",
        )
    pipeline_target = overdue_follow_ups[0] if overdue_follow_ups else None
    if pipeline_target is not None:
        return hero(
            "Follow-Up Worker",
            "pipeline",
            "Needs Attention",
            "Complete Due Follow-Up",
            "A scheduled sponsor follow-up is ready for your attention.",
            DashboardAction(
                "Open Follow-Up",
                "opportunity_detail",
                route_params={"opportunity_id": pipeline_target.id},
            ),
            level="warning",
        )
    return hero(
        "Research Worker",
        "research",
        "Ready",
        "Research More Sponsors",
        "No immediate Sponsor Opportunity work is waiting.",
        DashboardAction("Start Sponsor Research", "research_worker"),
    )


def _top_priority(
    *, organization, initiative, intelligence, generation_job, eligibility,
    top_category, meeting_complete, approved_asset_count, assignments,
    prospects, opportunities, overdue_follow_ups, outreach_waiting,
) -> DashboardPriority:
    """Return the one precise resume action selected from persisted state.

    Equal-priority records use oldest waiting timestamp and then lowest ID;
    due follow-ups use earliest due date before that tie-breaker.
    """

    def hero(worker, icon, status, title, message, action, *, level="primary",
             supporting_line=None):
        return DashboardPriority(
            title, message, level, action, supporting_line, worker, icon, status
        )

    def opportunity_action(item, label):
        return DashboardAction(
            label, "opportunity_detail",
            route_params={"opportunity_id": item.id},
        )

    setup_exists = organization is not None or initiative is not None
    setup_complete = bool(
        organization and initiative
        and (getattr(organization, "name", "") or "").strip()
        and (getattr(initiative, "name", "") or "").strip()
    )
    if not setup_complete:
        label = (
            "Edit Organization Setup" if setup_exists
            else "Complete Organization Setup"
        )
        return hero(
            "Organization Setup", "organization", "Action Required", label,
            "Provide the organization and initiative information required before strategy work begins.",
            DashboardAction(label, "setup"),
        )

    job_status = (
        (getattr(generation_job, "status", "") or "").lower()
        if generation_job is not None else ""
    )
    if job_status == "failed":
        return hero(
            "Strategy Worker", "strategy", "Needs Attention",
            "Strategy generation needs attention",
            "Strategy generation stopped before completion.",
            DashboardAction(
                "Retry Strategy Generation",
                "generate_workspace_sponsorship_intelligence", "POST",
                form_data={"regenerate": "true"} if intelligence else {},
            ), level="warning",
            supporting_line=getattr(generation_job, "message", None)
            or "Your existing intelligence was preserved.",
        )
    if job_status in ACTIVE_JOB_STATUSES:
        return hero(
            "Strategy Worker", "strategy", "Working",
            "View Strategy Progress",
            "Your Strategy Worker is preparing the sponsorship strategy.",
            DashboardAction("View Strategy Progress", "workspace"),
            level="info",
        )
    if not meeting_complete or intelligence is None:
        return hero(
            "Strategy Worker", "strategy", "Ready",
            "Build Sponsorship Strategy",
            "Meet with your Strategy Worker to create the sponsorship plan.",
            DashboardAction("Build Sponsorship Strategy", "strategy_meeting"),
        )
    if approved_asset_count == 0:
        return hero(
            "Strategy Worker", "strategy", "Ready for Review",
            "Continue Strategy Review",
            "Your Strategy Worker completed the plan. Review and approve the sponsorship assets.",
            DashboardAction("Continue Strategy Review", "strategy_work"),
        )

    opportunity_list = sorted(opportunities, key=_waiting_key)
    assignment_list = _latest_assignments_by_asset(assignments)

    def job_state(item, attribute):
        return (
            getattr(getattr(item, attribute, None), "status", "") or ""
        ).lower()

    # Failed durable work always outranks ordinary waiting work.
    failed_specs = (
        (
            "follow_up_generation_job", "Follow-Up Worker", "pipeline",
            "Retry Follow-Up Generation",
            lambda item: not getattr(item, "follow_up_message", None),
        ),
        (
            "outreach_generation_job", "Outreach Worker", "outreach",
            "Retry Outreach Generation",
            lambda item: not (
                getattr(item, "outreach", None)
                or getattr(item, "reviewed_message", None)
            ),
        ),
        (
            "contact_research_job", "Research Worker", "research",
            "Retry Contact Research",
            lambda item: not _has_usable_contact(item),
        ),
    )
    for attribute, worker, icon, label, failure_is_current in failed_specs:
        failed = [
            item for item in opportunity_list
            if job_state(item, attribute) == "failed"
            and failure_is_current(item)
        ]
        if failed:
            return hero(
                worker, icon, "Needs Attention", label,
                "The background worker could not complete this task safely.",
                opportunity_action(failed[0], label), level="warning",
            )
    failed_research = sorted(
        [item for item in assignment_list if (
            getattr(item, "status", "") or ""
        ).lower() == "needs_attention"], key=_waiting_key,
    )
    if failed_research:
        item = failed_research[0]
        return hero(
            "Research Worker", "research", "Needs Attention",
            "Retry Sponsor Research",
            "Review the failed assignment and retry when ready.",
            DashboardAction(
                "Retry Sponsor Research", "research_assignment",
                route_params={"assignment_id": item.id},
            ), level="warning",
            supporting_line=getattr(item, "asset_name", None),
        )

    # Preserve the established eligibility gate before ordinary opportunity
    # work; failed durable jobs above still remain the highest urgency.
    if eligibility is None or getattr(eligibility, "research_blocked", True):
        return hero(
            "Research Worker", "research", "Needs Attention",
            "Edit Organization Setup",
            "Sponsor Research is waiting for required eligibility information.",
            DashboardAction("Edit Organization Setup", "setup"),
            level="warning",
        )

    due = sorted(
        [
            item for item in overdue_follow_ups
            if not getattr(item, "follow_up_message", None)
            and job_state(item, "follow_up_generation_job")
            not in {"queued", "working"}
        ],
        key=_follow_up_key,
    )
    if due:
        item = due[0]
        target = (
            getattr(item, "recommended_target", None)
            or getattr(item, "parent_prospect", None)
            or "this sponsor"
        )
        return hero(
            "Follow-Up Worker", "pipeline", "Needs Attention",
            "Continue Follow-Up", f"A follow-up is due for {target}.",
            opportunity_action(item, "Continue Follow-Up"), level="warning",
        )

    follow_up_review = [
        item for item in opportunity_list
        if getattr(item, "follow_up_message", None)
        and not getattr(item, "follow_up_reviewed_at", None)
        and not getattr(item, "follow_up_completed_at", None)
    ]
    follow_up_send = [
        item for item in opportunity_list
        if getattr(item, "follow_up_message", None)
        and getattr(item, "follow_up_reviewed_at", None)
        and not getattr(item, "follow_up_completed_at", None)
    ]
    follow_up_working = [
        item for item in opportunity_list
        if job_state(item, "follow_up_generation_job") in {"queued", "working"}
    ]
    if follow_up_working:
        item = follow_up_working[0]
        return hero(
            "Follow-Up Worker", "pipeline", "Working",
            "View Follow-Up Progress",
            "Your Follow-Up Worker is preparing the next outreach.",
            opportunity_action(item, "View Follow-Up Progress"), level="info",
        )
    if follow_up_review:
        item = follow_up_review[0]
        return hero(
            "Follow-Up Worker", "pipeline", "Waiting for you",
            "Review Follow-Up", "A generated follow-up is ready for review.",
            opportunity_action(item, "Review Follow-Up"),
        )
    if follow_up_send:
        item = follow_up_send[0]
        return hero(
            "Follow-Up Worker", "pipeline", "Ready", "Send Follow-Up",
            "The reviewed follow-up is ready for delivery.",
            opportunity_action(item, "Send Follow-Up"),
        )
    outreach_review = sorted([
        item for item in outreach_waiting
        if not getattr(item, "message_reviewed_at", None)
    ], key=_waiting_key)
    outreach_approval = sorted([
        item for item in outreach_waiting
        if getattr(item, "message_reviewed_at", None)
        and not getattr(item, "message_approved_at", None)
    ], key=_waiting_key)
    outreach_send = sorted([
        item for item in outreach_waiting
        if getattr(item, "message_approved_at", None)
    ], key=_waiting_key)
    outreach_working = [
        item for item in opportunity_list
        if job_state(item, "outreach_generation_job") in {"queued", "working"}
    ]
    for items, status, title, message in (
        (outreach_working, "Working", "View Outreach Progress",
         "Your Outreach Worker is preparing Sponsor Outreach."),
        (outreach_send, "Ready", "Send Outreach",
         "The approved Sponsor Outreach is ready for delivery."),
        (outreach_approval, "Waiting for you", "Approve Outreach",
         "The reviewed Sponsor Outreach is waiting for approval."),
        (outreach_review, "Waiting for you", "Continue Outreach Review",
         "Prepared Sponsor Outreach is ready for quality review."),
    ):
        if items:
            return hero(
                "Outreach Worker", "outreach", status, title, message,
                opportunity_action(items[0], title),
                level="info" if status == "Working" else "primary",
            )

    contact_working = [
        item for item in opportunity_list
        if job_state(item, "contact_research_job")
        in {"queued", "processing", "working"}
    ]
    if contact_working:
        item = contact_working[0]
        return hero(
            "Research Worker", "research", "Working",
            "View Contact Research Progress",
            "Contact Discovery is researching a usable sponsor route.",
            opportunity_action(item, "View Contact Research Progress"),
            level="info",
        )

    def assignment_is_reviewed(assignment):
        result_count = getattr(assignment, "result_count", 0) or 0
        if result_count == 0:
            return True
        completed_at = _as_utc(getattr(assignment, "completed_at", None))
        return any(
            getattr(opportunity, "sponsorship_asset_id", None)
            == getattr(assignment, "sponsorship_asset_id", None)
            and (
                completed_at is None
                or _as_utc(getattr(opportunity, "created_at", None)) is None
                or _as_utc(getattr(opportunity, "created_at", None))
                >= completed_at
            )
            for opportunity in opportunity_list
        )

    review_assignments = sorted([
        item for item in assignment_list
        if (getattr(item, "status", "") or "").lower() == "completed"
        and not assignment_is_reviewed(item)
    ], key=_waiting_key)
    working_assignments = sorted([
        item for item in assignment_list
        if (getattr(item, "status", "") or "").lower() in {"ready", "working"}
    ], key=_waiting_key)
    if review_assignments:
        item = review_assignments[0]
        return hero(
            "Research Worker", "research", "Completed",
            "Review Sponsor Results",
            "Qualified sponsors are ready for your decision.",
            DashboardAction(
                "Review Sponsor Results", "research_assignment",
                route_params={"assignment_id": item.id},
            ), supporting_line=getattr(item, "asset_name", None),
        )
    if working_assignments:
        item = working_assignments[0]
        return hero(
            "Research Worker", "research", "Working",
            "View Research Progress",
            "Your Research Worker is evaluating sponsors for the selected opportunity.",
            DashboardAction(
                "View Research Progress", "research_assignment",
                route_params={"assignment_id": item.id},
            ), level="info",
            supporting_line=getattr(item, "asset_name", None),
        )

    contact_needed = [
        item for item in opportunity_list
        if getattr(item, "stage", None) == "Research Approved"
        and not _has_usable_contact(item)
    ]
    if len(contact_needed) > 1:
        return hero(
            "Pipeline Worker", "pipeline", "Ready", "Continue Pipeline",
            "Choose the Sponsor Opportunity whose contact route you want to advance.",
            DashboardAction("Continue Pipeline", "show_pipeline"),
        )
    if contact_needed:
        item = contact_needed[0]
        return hero(
            "Pipeline Worker", "pipeline", "Ready", "Continue Pipeline",
            "Choose or verify a contact route for this Sponsor Opportunity.",
            opportunity_action(item, "Continue Pipeline"),
        )
    outreach_ready = [
        item for item in opportunity_list
        if _outreach_is_available(item)
        or (
            getattr(item, "stage", None) == "Ready to Send"
            and not getattr(item, "outreach", None)
            and not getattr(item, "reviewed_message", None)
        )
    ]
    if outreach_ready:
        item = outreach_ready[0]
        return hero(
            "Outreach Worker", "outreach", "Ready", "Generate Outreach",
            "This Sponsor Opportunity is ready for outreach preparation.",
            opportunity_action(item, "Generate Outreach"),
        )
    pipeline_actionable = [
        item for item in opportunity_list
        if getattr(item, "stage", None) not in {"Won", "Lost"}
    ]
    if len(pipeline_actionable) > 1:
        return hero(
            "Pipeline Worker", "pipeline", "Ready", "Continue Pipeline",
            "Choose the Sponsor Opportunity you want to advance next.",
            DashboardAction("Continue Pipeline", "show_pipeline"),
        )
    return hero(
        "Research Worker", "research", "Ready", "Research More Sponsors",
        "No immediate Sponsor Opportunity work is waiting.",
        DashboardAction("Research More Sponsors", "research_worker"),
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
        and bool(
            getattr(opportunity, "outreach", None)
            or getattr(opportunity, "reviewed_message", None)
        )
    ]
    outreach_review_needed = [
        opportunity
        for opportunity in outreach_waiting
        if not getattr(opportunity, "message_reviewed_at", None)
    ]
    outreach_approval_needed = [
        opportunity
        for opportunity in outreach_waiting
        if getattr(opportunity, "message_reviewed_at", None)
        and not getattr(opportunity, "message_approved_at", None)
    ]
    outreach_send_ready = [
        opportunity
        for opportunity in outreach_waiting
        if getattr(opportunity, "message_approved_at", None)
    ]
    outreach_available = [
        opportunity
        for opportunity in opportunity_list
        if _outreach_is_available(opportunity)
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
            "Sponsorship Strategy",
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
            "Outreach Preparation",
            (
                "Current"
                if strategy_ready and opportunity_list
                else "Waiting"
                if strategy_ready and prospect_list
                else "Not started"
            ),
        ),
        DashboardProgressStep(
            "Follow-Up",
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
            "Complete",
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
                DashboardAction("View Strategy", "strategy_work"),
                "Waiting on",
                "Your strategy approval",
            )
        else:
            strategy_worker = DashboardWorker(
                "Strategy Worker",
                "Complete",
                "I've completed and applied your approved strategy.",
                DashboardAction("View Strategy", "strategy_work"),
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
                "Build Sponsorship Strategy",
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
                "View Strategy",
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
                "organization(s)."
            ),
            DashboardAction("Open Sponsor Pipeline", "show_pipeline"),
            "Current task",
            "Sponsors ready for review",
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
    elif outreach_review_needed:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Waiting for you",
            (
                f"I've prepared {len(outreach_review_needed)} outreach item(s) for "
                "your review."
            ),
            DashboardAction(
                "Review outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_review_needed[0].id},
            ),
            "Waiting on",
            "Your Outreach Review",
        )
    elif outreach_approval_needed:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Waiting for you",
            (
                f"{len(outreach_approval_needed)} reviewed outreach item(s) "
                "await your approval."
            ),
            DashboardAction(
                "Approve outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_approval_needed[0].id},
            ),
            "Waiting on",
            "Your approval",
        )
    elif outreach_send_ready:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Ready",
            (
                f"{len(outreach_send_ready)} approved outreach item(s) "
                "are ready to send."
            ),
            DashboardAction(
                "Send outreach",
                "opportunity_detail",
                route_params={"opportunity_id": outreach_send_ready[0].id},
            ),
            "Current task",
            "Send Outreach",
        )
    elif outreach_available:
        count = len(outreach_available)
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Ready",
            (
                f"{count} approved sponsor "
                f"opportunit{'y is' if count == 1 else 'ies are'} "
                "ready for outreach drafting."
            ),
            DashboardAction(
                "Generate Outreach",
                "generate_opportunity_outreach",
                "POST",
                route_params={"opportunity_id": outreach_available[0].id},
            ),
            "Current task",
            "Generate Outreach",
        )
    elif active_outreach:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Monitoring",
            (
                f"I'm managing {len(opportunity_list)} active outreach "
                "opportunit{'y' if len(opportunity_list) == 1 else 'ies'}."
            ),
            DashboardAction("Open Sponsor Pipeline", "show_pipeline"),
            "Current task",
            "Monitor responses and next actions",
        )
    else:
        outreach_worker = DashboardWorker(
            "Outreach Worker",
            "Waiting",
            "I'm waiting for an approved sponsor before I prepare outreach.",
            DashboardAction("Open Sponsor Pipeline", "show_pipeline"),
            "Waiting on",
            "An approved sponsor opportunity",
        )

    if not strategy_ready:
        pipeline_worker = DashboardWorker(
            "Pipeline Worker",
            "Waiting",
            "I'm waiting for the workflow to reach the Sponsor Pipeline.",
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
                f"I'm monitoring {len(opportunity_list)} active Sponsor Pipeline "
                f"opportunit{'y' if len(opportunity_list) == 1 else 'ies'}."
            ),
            DashboardAction("Open Sponsor Pipeline", "show_pipeline"),
            "Current task",
            f"{sponsors_secured} sponsor(s) secured",
        )
    else:
        pipeline_worker = DashboardWorker(
            "Pipeline Worker",
            "Ready",
            "I'm ready to track each approved sponsor opportunity.",
            DashboardAction("Open Sponsor Pipeline", "show_pipeline"),
            "Waiting on",
            "The first approved sponsor",
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

    workflow_progress = build_primary_navigation(
        organization=organization,
        initiative=initiative,
        intelligence=intelligence,
        assets=asset_list,
        opportunities=opportunity_list,
        today=today,
    )
    current_stage = next(
        (
            step.label
            for step in workflow_progress
            if step.state == "current"
        ),
        "Sponsor Research",
    )
    research_started = bool(
        assignment_list or prospect_list or opportunity_list
    )
    metrics = _mission_control_metrics(
        strategy_approved=bool(strategy_ready and approved_asset_count),
        research_started=research_started,
        approved_asset_count=approved_asset_count,
        prospect_count=len(prospect_list),
        opportunities=opportunity_list,
        overdue_follow_ups=overdue_follow_ups,
    )
    needs_attention = _mission_control_attention(
        intelligence=intelligence,
        generation_job=generation_job,
        approved_asset_count=approved_asset_count,
        assignments=assignment_list,
        opportunities=opportunity_list,
        overdue_follow_ups=overdue_follow_ups,
        top_priority=top_priority,
    )
    ai_team = _mission_control_team(
        strategy_worker=strategy_worker,
        research_worker=research_worker,
        outreach_worker=outreach_worker,
        strategy_ready=strategy_ready,
        opportunities=opportunity_list,
        overdue_follow_ups=overdue_follow_ups,
    )
    continue_labels = {
        "strategy": "View Strategy",
        "research": "Sponsor Research",
        "pipeline": "Sponsor Pipeline",
    }
    continue_links = tuple(
        DashboardLink(continue_labels.get(step.key, step.label), step.endpoint)
        for step in workflow_progress
        if step.key != "setup"
        and step.state != "locked"
        and step.endpoint != top_priority.action.endpoint
    )[:3]

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
        recent_activity=_mission_control_activity(
            intelligence=intelligence,
            generation_job=generation_job,
            assets=asset_list,
            prospects=prospect_list,
            assignments=assignment_list,
            opportunities=opportunity_list,
        ),
        pipeline_count=len(opportunity_list),
        sponsors_secured=sponsors_secured,
        approved_asset_count=approved_asset_count,
        prospect_count=len(prospect_list),
        job_status=job_status,
        current_stage=current_stage,
        workflow_progress=workflow_progress,
        ai_team=ai_team,
        metrics=metrics,
        needs_attention=needs_attention,
        continue_links=continue_links,
    )

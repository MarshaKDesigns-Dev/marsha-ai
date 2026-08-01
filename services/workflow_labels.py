"""Centralized user-facing labels for workflow and worker status values."""

from __future__ import annotations

from datetime import date
from typing import Any


BACKGROUND_WORK_HELPER = (
    "You may leave this page and return later. "
    "Your work will continue in the background."
)

WORKER_STATUS_COPY = {
    "strategy": {
        "working_title": "Your Strategy Worker is working.",
        "working_message": "Please wait while Marsha AI builds your sponsorship strategy.",
        "failure_title": "Your Strategy Worker needs your attention.",
        "failure_message": (
            "Marsha AI could not complete the strategy update. Your previously "
            "saved strategy and setup information were preserved."
        ),
        "retry_action": "Try Strategy Again",
    },
    "research": {
        "working_title": "Your Research Worker is working.",
        "working_message": "Please wait while Marsha AI searches for and evaluates sponsor opportunities.",
        "failure_title": "Your Research Worker needs your attention.",
        "failure_message": (
            "Marsha AI could not complete this sponsor research assignment. Your "
            "earlier research, saved sponsors, and pipeline records were preserved."
        ),
        "retry_action": "Try This Assignment Again",
    },
    "contact": {
        "working_title": "Your Contact Discovery Worker is working.",
        "working_message": "Please wait while Marsha AI looks for a verified contact route.",
        "failure_title": "Your Contact Discovery Worker needs your attention.",
        "failure_message": (
            "Marsha AI could not complete the contact search. Your Opportunity and "
            "any existing contact information were preserved."
        ),
        "retry_action": "Try Contact Discovery Again",
    },
    "outreach": {
        "working_title": "Your Outreach Worker is working.",
        "working_message": "Please wait while Marsha AI prepares the sponsor message.",
        "failure_title": "Your Outreach Worker needs your attention.",
        "failure_message": (
            "Marsha AI could not complete the sponsor message. Your Opportunity, "
            "contact details, prior message, review, approval, and delivery "
            "information were preserved."
        ),
        "retry_action": "Try Outreach Again",
    },
    "follow_up": {
        "working_title": "Your Follow-Up Worker is working.",
        "working_message": "Please wait while Marsha AI prepares the follow-up message.",
        "failure_title": "Your Follow-Up Worker needs your attention.",
        "failure_message": (
            "Marsha AI could not complete the follow-up message. Your original "
            "outreach, delivery details, follow-up schedule, and prior follow-up "
            "history were preserved."
        ),
        "retry_action": "Try Follow-Up Again",
    },
}


def worker_status_copy(worker):
    """Return approved customer-facing copy for one durable worker."""

    return WORKER_STATUS_COPY[worker]


WORKFLOW_LABELS = {
    "Organization": "Organization Setup",
    "Strategy": "Sponsorship Strategy",
    "Strategy Meeting": "Sponsorship Strategy",
    "Research": "Sponsor Research",
    "Sponsor Research": "Sponsor Research",
    "Pipeline": "Sponsor Pipeline",
    "Research Approved": "Sponsor Approved",
    "Outreach Working": "Outreach Preparation",
    "Message Review": "Outreach Review",
    "Ready to Send": "Outreach Preparation",
    "Sent": "Outreach Sent",
    "Follow-Up Due": "Follow-Up Due",
    "Responded": "Sponsor Pipeline",
    "Meeting": "Sponsor Pipeline",
    "Proposal": "Sponsor Pipeline",
    "Won": "Complete",
    "Lost": "Complete",
    "pending": "Sponsor Research Needed",
    "queued": "Research Queued",
    "processing": "Research In Progress",
    "working": "Work In Progress",
    "completed": "Research Complete",
    "needs_attention": "Needs Attention",
    "failed": "Needs Attention",
    "drafted": "Outreach Drafted",
    "message_reviewed": "Outreach Reviewed",
    "message_approved": "Ready to Send",
    "follow_up_due": "Follow-Up Due",
    "follow_up_drafted": "Follow-Up Drafted",
    "follow_up_sent": "Follow-Up Sent",
    "complete": "Complete",
}


def workflow_label(value: Any) -> str:
    """Return one stable display label without changing the stored value."""

    if value is None:
        return ""
    raw_value = str(value).strip()
    if not raw_value:
        return ""
    return WORKFLOW_LABELS.get(
        raw_value,
        raw_value.replace("_", " ").replace("-", " ").title(),
    )


def opportunity_stage_label(
    opportunity: Any,
    *,
    today: date | None = None,
) -> str:
    """Derive an accurate display stage from existing opportunity state."""

    stage = getattr(opportunity, "stage", None)
    if stage == "Ready to Send":
        if getattr(opportunity, "message_approved_at", None):
            return "Ready to Send"
        if getattr(opportunity, "message_reviewed_at", None):
            return "Outreach Reviewed"
        if getattr(opportunity, "outreach", None):
            return "Outreach Drafted"
        return "Outreach Preparation"

    if stage == "Sent":
        follow_up_date = getattr(opportunity, "follow_up_date", None)
        if getattr(opportunity, "follow_up_completed_at", None):
            return "Follow-Up Sent"
        if (
            today is not None
            and follow_up_date is not None
            and follow_up_date <= today
        ):
            if getattr(opportunity, "follow_up_reviewed_at", None):
                return "Follow-Up Drafted"
            return "Follow-Up Due"
        return "Outreach Sent"

    return workflow_label(stage)

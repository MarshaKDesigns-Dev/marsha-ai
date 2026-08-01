from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from services.workflow_labels import (
    BACKGROUND_WORK_HELPER,
    WORKER_STATUS_COPY,
    opportunity_stage_label,
    worker_status_copy,
    workflow_label,
)


def opportunity(**overrides):
    values = {
        "stage": "Research Approved",
        "outreach": None,
        "message_reviewed_at": None,
        "message_approved_at": None,
        "follow_up_date": None,
        "follow_up_reviewed_at": None,
        "follow_up_completed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_workflow_label_maps_internal_values_without_changing_them():
    assert workflow_label("Research Approved") == "Sponsor Approved"
    assert workflow_label("Message Review") == "Outreach Review"
    assert workflow_label("queued") == "Research Queued"
    assert workflow_label("needs_attention") == "Needs Attention"


def test_worker_status_copy_is_complete_and_approved():
    assert set(WORKER_STATUS_COPY) == {
        "strategy", "research", "contact", "outreach", "follow_up"
    }
    for name in WORKER_STATUS_COPY:
        copy = worker_status_copy(name)
        assert copy["working_title"].endswith("is working.")
        assert copy["working_message"].startswith("Please wait while Marsha AI")
        assert copy["failure_title"].endswith("needs your attention.")
        assert "preserved" in copy["failure_message"]
        assert copy["retry_action"].startswith("Try ")
    assert BACKGROUND_WORK_HELPER == (
        "You may leave this page and return later. "
        "Your work will continue in the background."
    )


def test_ready_to_send_label_requires_review_and_approval():
    drafted = opportunity(stage="Ready to Send", outreach="Draft")
    reviewed = opportunity(
        stage="Ready to Send",
        outreach="Reviewed",
        message_reviewed_at=datetime(2026, 7, 29),
    )
    approved = opportunity(
        stage="Ready to Send",
        outreach="Approved",
        message_reviewed_at=datetime(2026, 7, 29),
        message_approved_at=datetime(2026, 7, 29),
    )

    assert opportunity_stage_label(drafted) == "Outreach Drafted"
    assert opportunity_stage_label(reviewed) == "Outreach Reviewed"
    assert opportunity_stage_label(approved) == "Ready to Send"


def test_sent_stage_uses_outreach_and_follow_up_display_labels():
    sent = opportunity(
        stage="Sent",
        follow_up_date=date(2026, 8, 5),
    )
    due = opportunity(
        stage="Sent",
        follow_up_date=date(2026, 7, 29),
    )
    complete = opportunity(
        stage="Sent",
        follow_up_date=date(2026, 8, 5),
        follow_up_completed_at=datetime(2026, 7, 29),
    )

    assert opportunity_stage_label(sent, today=date(2026, 7, 29)) == "Outreach Sent"
    assert opportunity_stage_label(due, today=date(2026, 7, 29)) == "Follow-Up Due"
    assert opportunity_stage_label(complete) == "Follow-Up Sent"


def test_workflow_templates_use_centralized_display_labels():
    pipeline = Path("templates/pipeline.html").read_text(encoding="utf-8")
    opportunity_template = Path("templates/opportunity.html").read_text(
        encoding="utf-8"
    )

    assert "opportunity_stage_label(opp" in pipeline
    assert "opportunity_stage_label(opp" in opportunity_template
    assert "worker_status_copy('contact')" in opportunity_template
    assert "contact_research_job.status|replace" not in opportunity_template

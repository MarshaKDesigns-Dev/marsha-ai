from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from services.dashboard import build_dashboard


NOW = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)


def organization(sender_name="Marsha Shearin"):
    return SimpleNamespace(sender_name=sender_name)


def initiative(deadline=date(2026, 8, 3)):
    return SimpleNamespace(deadline=deadline)


def intelligence(*, blocked=False, missing=None):
    eligibility = SimpleNamespace(
        research_blocked=blocked,
        missing_information=missing or [],
    )
    return SimpleNamespace(
        sponsor_eligibility=eligibility,
        updated_at=NOW - timedelta(days=1),
    )


def category():
    return SimpleNamespace(
        slug="technology",
        category="Technology",
    )


def opportunity(
    *,
    identifier=1,
    stage="Ready to Send",
    follow_up_date=None,
    updated_at=None,
):
    return SimpleNamespace(
        id=identifier,
        stage=stage,
        follow_up_date=follow_up_date,
        recommended_target="Example Sponsor",
        parent_prospect="Example Sponsor",
        updated_at=updated_at or NOW,
    )


def prospect():
    return SimpleNamespace(
        id=10,
        company_name="Evidence Company",
        category_slug="technology",
        updated_at=NOW - timedelta(hours=1),
    )


def build(**overrides):
    values = {
        "organization": organization(),
        "initiative": initiative(),
        "intelligence": intelligence(),
        "generation_job": None,
        "top_category": category(),
        "assets": [
            SimpleNamespace(
                approval_status="Approved",
                is_active=True,
            )
        ],
        "prospects": [],
        "opportunities": [],
        "now": NOW,
    }
    values.update(overrides)
    return build_dashboard(**values)


def test_completed_strategy_requires_asset_review_before_research():
    dashboard = build(assets=[])

    assert dashboard.top_priority.title == "Review Sponsorship Assets."
    assert dashboard.top_priority.action.endpoint == (
        "sponsorship_asset_review"
    )
    assert dashboard.workers[1].status == "Waiting for you"


def test_asset_review_precedes_eligibility_remediation_until_approval():
    dashboard = build(
        intelligence=intelligence(
            blocked=True,
            missing=["audience_age_context"],
        ),
        assets=[],
    )

    assert dashboard.top_priority.title == "Review Sponsorship Assets."


def test_dashboard_builds_time_aware_greeting_and_summary():
    dashboard = build()

    assert dashboard.greeting == "Good morning, Marsha"
    assert dashboard.days_remaining == 10
    assert dashboard.pipeline_count == 0
    assert [step.label for step in dashboard.progress] == [
        "Organization Setup",
        "Strategy Meeting",
        "Sponsor Research",
        "Outreach",
        "Follow-ups",
        "Sponsors Secured",
    ]
    assert [worker.name for worker in dashboard.workers] == [
        "Strategy Worker",
        "Research Worker",
        "Outreach Worker",
        "Pipeline Worker",
    ]


def test_dashboard_greeting_falls_back_to_there():
    dashboard = build(
        organization=organization(""),
        now=datetime(2026, 7, 24, 20, 0, tzinfo=UTC),
    )

    assert dashboard.greeting == "Good evening, there"


def test_failed_work_is_the_highest_priority():
    failed_job = SimpleNamespace(
        status="failed",
        message="Safe failure.",
        updated_at=NOW,
    )
    overdue = opportunity(
        follow_up_date=NOW.date() - timedelta(days=1),
    )

    dashboard = build(
        intelligence=intelligence(blocked=True),
        generation_job=failed_job,
        opportunities=[overdue],
    )

    assert dashboard.top_priority.title == "Strategy needs attention"
    assert dashboard.top_priority.action.label == "Try again"
    assert dashboard.top_priority.supporting_line == "Safe failure."


def test_active_regeneration_precedes_stale_intelligence_state():
    dashboard = build(
        intelligence=intelligence(
            blocked=True,
            missing=["audience_age_context"],
        ),
        generation_job=SimpleNamespace(status="processing"),
        assets=[
            SimpleNamespace(
                approval_status="Approved",
                is_active=True,
            )
        ],
    )

    assert dashboard.top_priority.title == "Strategy work is underway"


def test_blocked_eligibility_precedes_overdue_follow_up():
    overdue = opportunity(
        follow_up_date=NOW.date() - timedelta(days=1),
    )

    dashboard = build(
        intelligence=intelligence(
            blocked=True,
            missing=["audience_age_context"],
        ),
        opportunities=[overdue],
    )

    assert dashboard.top_priority.title == "Resolve required information"
    assert dashboard.top_priority.message == (
        "Sponsor research is waiting for required information."
    )
    assert dashboard.top_priority.supporting_line == "Audience age context"
    assert dashboard.workers[1].status == "Blocked"


def test_overdue_follow_up_precedes_outreach_approval():
    overdue = opportunity(
        identifier=1,
        stage="Sent",
        follow_up_date=NOW.date() - timedelta(days=1),
    )
    waiting = opportunity(identifier=2, stage="Ready to Send")

    dashboard = build(opportunities=[waiting, overdue])

    assert dashboard.top_priority.title == "Follow-up due"
    assert dashboard.top_priority.action.route_params == {
        "opportunity_id": 1
    }
    assert dashboard.workers[3].status == "Action required"


def test_outreach_approval_precedes_missing_intelligence():
    waiting = opportunity(stage="Ready to Send")

    dashboard = build(
        intelligence=None,
        opportunities=[waiting],
    )

    assert dashboard.top_priority.title == "Approve sponsor outreach"
    assert dashboard.workers[2].status == "Waiting for you"


def test_missing_intelligence_precedes_research_and_pipeline():
    dashboard = build(
        intelligence=None,
        prospects=[prospect()],
        opportunities=[opportunity(stage="Sent")],
    )

    assert dashboard.top_priority.title == (
        "Create your sponsorship strategy"
    )


def test_research_ready_precedes_pipeline_review():
    dashboard = build(
        opportunities=[opportunity(stage="Sent")],
    )

    assert dashboard.top_priority.title == "Sponsor research is ready"
    assert dashboard.top_priority.action.endpoint == "prospects"
    assert dashboard.top_priority.action.method == "POST"


def test_pipeline_review_and_no_action_fallbacks():
    with_pipeline = build(
        prospects=[prospect()],
        opportunities=[opportunity(stage="Sent")],
    )
    no_action = build(
        top_category=None,
        prospects=[prospect()],
        opportunities=[],
    )

    assert with_pipeline.top_priority.title == "Review your active pipeline"
    assert no_action.top_priority.title == "No action required"


def test_recent_activity_uses_existing_record_timestamps():
    job = SimpleNamespace(
        status="completed",
        updated_at=NOW - timedelta(hours=2),
    )
    recent_opportunity = opportunity(
        updated_at=NOW,
        stage="Meeting",
    )

    dashboard = build(
        generation_job=job,
        prospects=[prospect()],
        opportunities=[recent_opportunity],
    )

    messages = [item.message for item in dashboard.recent_activity]
    assert messages[0] == "Example Sponsor moved to Meeting."
    assert "Evidence Company was added to Technology research." in messages
    assert (
        "The Strategy Worker completed intelligence generation." in messages
    )


def test_worker_messages_are_operational_and_include_work_detail():
    dashboard = build()

    assert dashboard.workers[0].message.startswith("I've")
    assert dashboard.workers[1].message.startswith("I'm")
    assert dashboard.workers[2].message.startswith("I'm")
    assert dashboard.workers[3].message.startswith("I'm")
    assert all(worker.detail_label for worker in dashboard.workers)
    assert all(worker.detail for worker in dashboard.workers)


def test_recent_activity_is_limited_to_four_items():
    opportunities = [
        opportunity(
            identifier=index,
            stage="Meeting",
            updated_at=NOW - timedelta(minutes=index),
        )
        for index in range(1, 7)
    ]

    dashboard = build(
        prospects=[prospect()],
        opportunities=opportunities,
    )

    assert len(dashboard.recent_activity) == 4


def test_progress_uses_customer_facing_statuses():
    dashboard = build(
        prospects=[prospect()],
        opportunities=[opportunity(stage="Sent")],
    )

    supported_statuses = {
        "Complete",
        "Current",
        "Waiting",
        "Not started",
        "Action required",
    }
    assert all(
        step.status in supported_statuses
        for step in dashboard.progress
    )

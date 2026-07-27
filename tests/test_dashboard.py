from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from services.dashboard import build_dashboard


NOW = datetime(2026, 7, 24, 9, 30, tzinfo=UTC)


def organization(sender_name="Marsha Shearin"):
    return SimpleNamespace(
        id=1,
        name="Bright Futures",
        sender_name=sender_name,
    )


def initiative(deadline=date(2026, 8, 3)):
    return SimpleNamespace(
        id=2,
        name="Leadership Summit",
        deadline=deadline,
        strategy_meeting_completed_at=NOW,
    )


def assignment(
    status,
    *,
    identifier=40,
    asset_id=7,
    result_count=5,
    completed_at=None,
):
    return SimpleNamespace(
        id=identifier,
        status=status,
        sponsorship_asset_id=asset_id,
        asset_name="Stage, Lighting & AV Production",
        result_count=result_count,
        completed_at=completed_at or NOW,
    )


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
    asset_id=7,
    created_at=None,
    outreach=None,
    reviewed_message=None,
    message_reviewed_at=None,
):
    return SimpleNamespace(
        id=identifier,
        stage=stage,
        follow_up_date=follow_up_date,
        recommended_target="Example Sponsor",
        parent_prospect="Example Sponsor",
        updated_at=updated_at or NOW,
        created_at=created_at or NOW,
        sponsorship_asset_id=asset_id,
        outreach=outreach,
        reviewed_message=reviewed_message,
        message_reviewed_at=message_reviewed_at,
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
        "research_assignments": [],
        "now": NOW,
    }
    values.update(overrides)
    return build_dashboard(**values)


def test_completed_strategy_requires_asset_review_before_research():
    dashboard = build(assets=[])

    assert dashboard.top_priority.title == (
        "Your sponsorship strategy is ready for review"
    )
    assert dashboard.top_priority.action.endpoint == (
        "strategy_work"
    )
    assert dashboard.top_priority.worker_name == "Strategy Worker"
    assert dashboard.top_priority.status == "Ready for Review"
    assert dashboard.top_priority.action.label == "Review Strategy"


def test_asset_review_precedes_eligibility_remediation_until_approval():
    dashboard = build(
        intelligence=intelligence(
            blocked=True,
            missing=["audience_age_context"],
        ),
        assets=[],
    )

    assert dashboard.top_priority.title == (
        "Your sponsorship strategy is ready for review"
    )


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

    assert dashboard.greeting == "Welcome back"


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

    assert dashboard.top_priority.title == (
        "Your Strategy Worker needs attention"
    )
    assert dashboard.top_priority.action.label == "Retry Strategy Generation"
    assert dashboard.top_priority.action.form_data == {
        "regenerate": "true"
    }
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

    assert dashboard.top_priority.title == (
        "Your Strategy Worker is preparing your sponsorship strategy"
    )


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

    assert dashboard.top_priority.title == (
        "Your Research Worker needs required information"
    )
    assert dashboard.top_priority.message == (
        "Sponsor research is waiting for required information."
    )
    assert dashboard.top_priority.supporting_line == "Audience age context"
    assert dashboard.workers[1].status == "Needs Attention"


def test_active_outreach_precedes_pipeline_follow_up():
    overdue = opportunity(
        identifier=1,
        stage="Sent",
        follow_up_date=NOW.date() - timedelta(days=1),
    )
    waiting = opportunity(
        identifier=2,
        stage="Ready to Send",
        outreach="Draft sponsor message",
    )

    dashboard = build(opportunities=[waiting, overdue])

    assert dashboard.top_priority.title == (
        "Your Outreach Worker is preparing sponsor communication"
    )
    assert dashboard.top_priority.action.route_params == {
        "opportunity_id": 2
    }
    assert dashboard.workers[2].status == "Working"


def test_strategy_ready_precedes_stale_outreach_without_intelligence():
    waiting = opportunity(stage="Ready to Send")

    dashboard = build(
        intelligence=None,
        opportunities=[waiting],
    )

    assert dashboard.top_priority.title == "Your Strategy Worker is ready"


def test_missing_intelligence_precedes_research_and_pipeline():
    dashboard = build(
        intelligence=None,
        prospects=[prospect()],
        opportunities=[opportunity(stage="Sent")],
    )

    assert dashboard.top_priority.title == (
        "Your Strategy Worker is ready"
    )
    assert [step.status for step in dashboard.progress] == [
        "Complete",
        "Current",
        "Not started",
        "Not started",
        "Not started",
        "Not started",
    ]
    assert dashboard.workers[1].status == "Waiting"
    assert dashboard.workers[2].status == "Waiting"
    assert dashboard.workers[3].status == "Waiting"


def test_research_ready_precedes_pipeline_review():
    dashboard = build(
        opportunities=[opportunity(stage="Sent")],
    )

    assert dashboard.top_priority.title == "Manage your sponsorship pipeline"
    assert dashboard.top_priority.action.endpoint == "show_pipeline"


def test_pipeline_review_and_prospect_review_fallbacks():
    with_pipeline = build(
        prospects=[prospect()],
        opportunities=[opportunity(stage="Sent")],
    )
    no_action = build(
        top_category=None,
        prospects=[prospect()],
        opportunities=[],
    )

    assert with_pipeline.top_priority.title == "Manage your sponsorship pipeline"
    assert no_action.top_priority.title == (
        "What would you like your Research Worker to research next?"
    )
    assert no_action.top_priority.action.label == "Assign Research"


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
    assert dashboard.workers[1].message
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


def test_incomplete_setup_uses_organization_setup_hero():
    dashboard = build(
        organization=SimpleNamespace(name="", sender_name=""),
    )

    assert dashboard.top_priority.worker_name == "Organization Setup"
    assert dashboard.top_priority.worker_icon == "organization"
    assert dashboard.top_priority.status == "Action Required"
    assert dashboard.top_priority.action.label == "Continue Setup"
    assert dashboard.top_priority.action.endpoint == "setup"


def test_completed_setup_without_meeting_uses_strategy_ready_hero():
    dashboard = build(
        initiative=SimpleNamespace(
            id=2,
            name="Leadership Summit",
            deadline=None,
            strategy_meeting_completed_at=None,
        ),
        intelligence=None,
    )

    assert dashboard.top_priority.worker_name == "Strategy Worker"
    assert dashboard.top_priority.status == "Ready"
    assert dashboard.top_priority.action.label == "Begin Strategy Meeting"
    assert dashboard.top_priority.action.endpoint == "strategy_meeting"


def test_working_research_assignment_uses_research_working_hero():
    dashboard = build(
        research_assignments=[assignment("working")],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.worker_icon == "research"
    assert dashboard.top_priority.status == "Working"
    assert dashboard.top_priority.action.label == "View Research Progress"
    assert dashboard.top_priority.action.endpoint == "research_assignment"
    assert dashboard.top_priority.supporting_line == (
        "Stage, Lighting & AV Production"
    )


def test_failed_research_assignment_uses_needs_attention_hero():
    dashboard = build(
        research_assignments=[assignment("needs_attention")],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Needs Attention"
    assert dashboard.top_priority.action.label == (
        "Review Research Assignment"
    )


def test_unreviewed_completed_research_uses_completed_hero():
    dashboard = build(
        research_assignments=[assignment("completed")],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Completed"
    assert dashboard.top_priority.action.label == "Review Research Results"
    assert dashboard.top_priority.action.route_params == {
        "assignment_id": 40
    }


def test_older_unreviewed_assignment_is_not_hidden_by_newer_reviewed_work():
    dashboard = build(
        research_assignments=[
            assignment(
                "completed",
                identifier=42,
                asset_id=9,
                result_count=0,
            ),
            assignment(
                "completed",
                identifier=41,
                asset_id=8,
            ),
        ],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Completed"
    assert dashboard.top_priority.action.route_params == {
        "assignment_id": 41
    }


def test_older_failed_assignment_outranks_newer_reviewed_work():
    dashboard = build(
        research_assignments=[
            assignment(
                "completed",
                identifier=42,
                asset_id=9,
                result_count=0,
            ),
            assignment(
                "needs_attention",
                identifier=41,
                asset_id=8,
            ),
        ],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Needs Attention"
    assert dashboard.top_priority.action.route_params == {
        "assignment_id": 41
    }


def test_older_working_assignment_outranks_newer_reviewed_work():
    dashboard = build(
        research_assignments=[
            assignment(
                "completed",
                identifier=42,
                asset_id=9,
                result_count=0,
            ),
            assignment(
                "working",
                identifier=41,
                asset_id=8,
            ),
        ],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Working"
    assert dashboard.top_priority.action.route_params == {
        "assignment_id": 41
    }


def test_reviewed_research_without_saved_opportunity_returns_research_ready():
    dashboard = build(
        research_assignments=[
            assignment("completed", result_count=0)
        ],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Ready"
    assert dashboard.top_priority.action.endpoint == "research_worker"


def test_saving_one_research_result_keeps_research_worker_ready():
    dashboard = build(
        research_assignments=[assignment("completed")],
        opportunities=[
            opportunity(
                stage="Research Approved",
                created_at=NOW + timedelta(minutes=1),
            )
        ],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Ready"
    assert dashboard.top_priority.action.label == "Assign Research"
    assert dashboard.top_priority.action.endpoint == "research_worker"


def test_saving_results_from_several_assignments_keeps_research_ready():
    dashboard = build(
        research_assignments=[
            assignment("completed", identifier=42, asset_id=9),
            assignment("completed", identifier=41, asset_id=8),
        ],
        opportunities=[
            opportunity(
                identifier=1,
                stage="Research Approved",
                asset_id=8,
            ),
            opportunity(
                identifier=2,
                stage="Research Approved",
                asset_id=9,
            ),
        ],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Ready"
    assert dashboard.top_priority.title == (
        "What would you like your Research Worker to research next?"
    )


def test_beginning_outreach_uses_outreach_ready_hero():
    dashboard = build(
        opportunities=[opportunity(stage="Ready to Send")],
    )

    assert dashboard.top_priority.worker_name == "Outreach Worker"
    assert dashboard.top_priority.status == "Ready"
    assert dashboard.top_priority.action.label == "Begin Outreach"


def test_generated_outreach_uses_outreach_working_hero():
    dashboard = build(
        opportunities=[
            opportunity(
                stage="Ready to Send",
                outreach="Evidence-backed sponsor message",
            )
        ],
    )

    assert dashboard.top_priority.worker_name == "Outreach Worker"
    assert dashboard.top_priority.status == "Working"
    assert dashboard.top_priority.action.label == "View Outreach Work"


def test_sent_opportunity_uses_pipeline_worker_hero():
    dashboard = build(
        opportunities=[opportunity(stage="Sent")],
    )

    assert dashboard.top_priority.worker_name == "Pipeline Worker"
    assert dashboard.top_priority.status == "Monitoring"
    assert dashboard.top_priority.action.label == "Open Pipeline"


def test_hero_and_matching_worker_panel_are_consistent():
    dashboard = build(
        research_assignments=[assignment("working")],
    )
    active_worker = next(
        worker
        for worker in dashboard.workers
        if worker.name == dashboard.top_priority.worker_name
    )

    assert active_worker.status == dashboard.top_priority.status
    assert active_worker.action == dashboard.top_priority.action
    assert active_worker.detail == dashboard.top_priority.title

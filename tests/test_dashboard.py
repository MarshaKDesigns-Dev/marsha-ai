from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

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
    message_approved_at=None,
    email=None,
    phone=None,
    contact_url=None,
    sent_date=None,
    follow_up_completed_at=None,
    follow_up_message=None,
    follow_up_reviewed_at=None,
    outreach_generation_job=None,
    follow_up_generation_job=None,
    contact_research_job=None,
    recommended_target="Example Sponsor",
):
    return SimpleNamespace(
        id=identifier,
        stage=stage,
        follow_up_date=follow_up_date,
        recommended_target=recommended_target,
        parent_prospect=recommended_target,
        updated_at=updated_at or NOW,
        created_at=created_at or NOW,
        sponsorship_asset_id=asset_id,
        outreach=outreach,
        reviewed_message=reviewed_message,
        message_reviewed_at=message_reviewed_at,
        message_approved_at=message_approved_at,
        email=email,
        phone=phone,
        contact_url=contact_url,
        sent_date=sent_date,
        follow_up_completed_at=follow_up_completed_at,
        follow_up_message=follow_up_message,
        follow_up_reviewed_at=follow_up_reviewed_at,
        outreach_generation_job=outreach_generation_job,
        follow_up_generation_job=follow_up_generation_job,
        contact_research_job=contact_research_job,
    )


def prospect():
    return SimpleNamespace(
        id=10,
        company_name="Evidence Company",
        category_slug="technology",
        updated_at=NOW - timedelta(hours=1),
        created_at=NOW - timedelta(hours=1),
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
        "Continue Strategy Review"
    )
    assert dashboard.top_priority.action.endpoint == (
        "strategy_work"
    )
    assert dashboard.top_priority.worker_name == "Strategy Worker"
    assert dashboard.top_priority.status == "Ready for Review"
    assert dashboard.top_priority.action.label == "Continue Strategy Review"


def test_asset_review_precedes_eligibility_remediation_until_approval():
    dashboard = build(
        intelligence=intelligence(
            blocked=True,
            missing=["audience_age_context"],
        ),
        assets=[],
    )

    assert dashboard.top_priority.title == (
        "Continue Strategy Review"
    )


def test_dashboard_builds_time_aware_greeting_and_summary():
    dashboard = build()

    assert dashboard.greeting == "Good morning, Marsha"
    assert dashboard.days_remaining == 10
    assert dashboard.pipeline_count == 0
    assert [step.label for step in dashboard.progress] == [
        "Organization Setup",
        "Sponsorship Strategy",
        "Sponsor Research",
        "Outreach Preparation",
        "Follow-Up",
        "Complete",
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
        "Your Strategy Worker needs your attention."
    )
    assert dashboard.top_priority.action.label == "Try Strategy Again"
    assert dashboard.top_priority.action.form_data == {
        "regenerate": "true"
    }
    assert dashboard.top_priority.supporting_line is None
    assert "Safe failure" not in dashboard.top_priority.message


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
        "Your Strategy Worker is working."
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

    assert dashboard.top_priority.title == "Edit Organization Setup"
    assert dashboard.top_priority.message == (
        "Sponsor Research is waiting for required eligibility information."
    )
    assert dashboard.top_priority.supporting_line is None
    assert dashboard.workers[1].status == "Needs Attention"


def test_due_follow_up_precedes_outreach_review():
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

    assert dashboard.top_priority.title == "Continue Follow-Up"
    assert dashboard.top_priority.action.route_params == {
        "opportunity_id": 1
    }
    assert dashboard.workers[2].status == "Waiting for you"


def test_outreach_worker_requires_review_then_approval_then_send():
    draft = opportunity(
        identifier=1,
        stage="Ready to Send",
        outreach="Draft sponsor message",
    )
    reviewed = opportunity(
        identifier=2,
        stage="Ready to Send",
        outreach="Reviewed sponsor message",
        reviewed_message="Reviewed sponsor message",
        message_reviewed_at=NOW,
    )
    approved = opportunity(
        identifier=3,
        stage="Ready to Send",
        outreach="Approved sponsor message",
        reviewed_message="Approved sponsor message",
        message_reviewed_at=NOW,
        message_approved_at=NOW,
    )

    review_dashboard = build(opportunities=[draft])
    approve_dashboard = build(opportunities=[reviewed])
    send_dashboard = build(opportunities=[approved])

    assert review_dashboard.workers[2].status == "Waiting for you"
    assert review_dashboard.workers[2].action.label == "Continue Outreach Review"
    assert approve_dashboard.workers[2].status == "Waiting for you"
    assert approve_dashboard.workers[2].action.label == "Approve Outreach"
    assert send_dashboard.workers[2].status == "Ready"
    assert send_dashboard.workers[2].action.label == "Send Outreach"


def test_strategy_ready_precedes_stale_outreach_without_intelligence():
    waiting = opportunity(stage="Ready to Send")

    dashboard = build(
        intelligence=None,
        opportunities=[waiting],
    )

    assert dashboard.top_priority.title == "Build Sponsorship Strategy"


def test_missing_intelligence_precedes_research_and_pipeline():
    dashboard = build(
        intelligence=None,
        prospects=[prospect()],
        opportunities=[opportunity(stage="Sent")],
    )

    assert dashboard.top_priority.title == (
        "Build Sponsorship Strategy"
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

    assert dashboard.top_priority.title == "Research More Sponsors"
    assert dashboard.top_priority.action.endpoint == "research_worker"


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

    assert with_pipeline.top_priority.title == "Research More Sponsors"
    assert no_action.top_priority.title == "Research More Sponsors"
    assert no_action.top_priority.action.label == "Research More Sponsors"


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
    assert messages[0] == "Example Sponsor added to Sponsor Pipeline"
    assert "Sponsorship strategy generated" in messages
    assert all("moved to" not in message for message in messages)


def test_worker_messages_are_operational_and_include_work_detail():
    dashboard = build()

    assert dashboard.workers[0].message.startswith("I've")
    assert dashboard.workers[1].message
    assert dashboard.workers[2].message.startswith("I'm")
    assert dashboard.workers[3].message.startswith("I'm")
    assert all(worker.detail_label for worker in dashboard.workers)
    assert all(worker.detail for worker in dashboard.workers)


def test_recent_activity_is_limited_to_five_items():
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

    assert len(dashboard.recent_activity) == 5


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
    assert dashboard.top_priority.action.label == "Edit Organization Setup"
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
    assert dashboard.top_priority.action.label == "Build Sponsorship Strategy"
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
        "Try This Assignment Again"
    )


def test_unreviewed_completed_research_uses_completed_hero():
    dashboard = build(
        research_assignments=[assignment("completed")],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Completed"
    assert dashboard.top_priority.action.label == "Review Sponsor Results"
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

    assert dashboard.top_priority.worker_name == "Pipeline Worker"
    assert dashboard.top_priority.action.label == "Continue Pipeline"
    assert dashboard.top_priority.action.route_params == {"opportunity_id": 1}


def test_approved_contact_makes_outreach_ready_without_changing_research_hero():
    dashboard = build(
        research_assignments=[assignment("completed")],
        opportunities=[
            opportunity(
                stage="Research Approved",
                email="partnerships@example.org",
            )
        ],
    )

    assert dashboard.top_priority.worker_name == "Outreach Worker"
    assert dashboard.top_priority.action.label == "Generate Outreach"
    assert dashboard.top_priority.action.route_params == {"opportunity_id": 1}
    outreach_worker = next(
        worker
        for worker in dashboard.workers
        if worker.name == "Outreach Worker"
    )
    assert outreach_worker.status == "Ready"
    assert outreach_worker.action.label == "Generate Outreach"
    assert outreach_worker.action.endpoint == "opportunity_detail"
    assert outreach_worker.action.method == "GET"


def test_research_approved_without_contact_keeps_outreach_waiting():
    dashboard = build(
        opportunities=[opportunity(stage="Research Approved")],
    )

    outreach_worker = next(
        worker
        for worker in dashboard.workers
        if worker.name == "Outreach Worker"
    )
    assert outreach_worker.status == "Waiting"


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

    assert dashboard.top_priority.worker_name == "Pipeline Worker"
    assert dashboard.top_priority.action.label == "Continue Pipeline"
    assert dashboard.top_priority.action.endpoint == "show_pipeline"


def test_beginning_outreach_uses_outreach_ready_hero():
    dashboard = build(
        opportunities=[opportunity(stage="Ready to Send")],
    )

    assert dashboard.top_priority.worker_name == "Outreach Worker"
    assert dashboard.top_priority.status == "Ready"
    assert dashboard.top_priority.action.label == "Generate Outreach"


def test_generated_outreach_uses_review_outreach_hero():
    dashboard = build(
        opportunities=[
            opportunity(
                stage="Ready to Send",
                outreach="Evidence-backed sponsor message",
            )
        ],
    )

    assert dashboard.top_priority.worker_name == "Outreach Worker"
    assert dashboard.top_priority.status == "Waiting for you"
    assert dashboard.top_priority.action.label == "Continue Outreach Review"


def test_sent_opportunity_without_due_work_returns_to_research():
    dashboard = build(
        opportunities=[opportunity(stage="Sent")],
    )

    assert dashboard.top_priority.worker_name == "Research Worker"
    assert dashboard.top_priority.status == "Ready"
    assert dashboard.top_priority.action.label == "Research More Sponsors"


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


def test_mission_control_no_setup_has_one_meaningful_priority():
    dashboard = build(
        organization=None,
        initiative=None,
        intelligence=None,
        assets=[],
        top_category=None,
    )

    assert dashboard.current_stage == "Organization Setup"
    assert dashboard.top_priority.action.label == "Complete Organization Setup"
    assert dashboard.metrics == ()
    assert dashboard.recent_activity == ()
    assert [step.state for step in dashboard.workflow_progress] == [
        "current",
        "locked",
        "locked",
        "locked",
    ]


def test_mission_control_uses_navigation_as_workflow_source():
    dashboard = build()

    assert dashboard.current_stage == "Sponsor Research"
    assert [step.label for step in dashboard.workflow_progress] == [
        "Organization Setup",
        "Sponsorship Strategy",
        "Sponsor Research",
        "Sponsor Pipeline",
    ]
    assert [step.state for step in dashboard.workflow_progress] == [
        "complete",
        "complete",
        "current",
        "locked",
    ]


def test_mission_control_metrics_are_context_sensitive():
    before_strategy = build(intelligence=None, assets=[])
    research_ready = build()
    with_outreach = build(
        prospects=[prospect()],
        opportunities=[
            opportunity(
                outreach="Draft",
                message_reviewed_at=NOW,
                message_approved_at=NOW,
            )
        ],
    )

    assert before_strategy.metrics == ()
    assert [metric.label for metric in research_ready.metrics] == [
        "Approved Assets"
    ]
    assert [metric.label for metric in with_outreach.metrics] == [
        "Approved Assets",
        "Sponsors Researched",
        "Sponsors in Pipeline",
        "Outreach Ready",
        "Outreach Sent",
        "Follow-Ups Due",
    ]


def test_mission_control_ai_team_uses_approved_worker_statuses():
    dashboard = build(
        opportunities=[opportunity(outreach="Draft")],
    )

    assert [worker.name for worker in dashboard.ai_team] == [
        "Strategy Worker",
        "Research Worker",
        "Outreach Worker",
        "Message Quality Review Worker",
        "Follow-Up Worker",
    ]
    assert {worker.status for worker in dashboard.ai_team} <= {
        "Waiting",
        "Ready",
        "Working",
        "Complete",
        "Needs Attention",
    }


def test_needs_attention_is_ordered_and_does_not_repeat_top_priority():
    review = opportunity(identifier=1, outreach="Draft")
    due = opportunity(
        identifier=2,
        stage="Sent",
        follow_up_date=NOW.date() - timedelta(days=1),
        sent_date=NOW.date() - timedelta(days=8),
    )
    dashboard = build(opportunities=[review, due])

    assert dashboard.top_priority.action.route_params == {
        "opportunity_id": 2
    }
    assert [item.title for item in dashboard.needs_attention] == [
        "Outreach Review required"
    ]


def test_recent_activity_uses_explicit_timestamps_and_newest_first():
    reviewed_at = NOW - timedelta(hours=2)
    approved_at = NOW - timedelta(hours=1)
    dashboard = build(
        opportunities=[
            opportunity(
                created_at=NOW - timedelta(days=1),
                outreach="Draft",
                message_reviewed_at=reviewed_at,
                message_approved_at=approved_at,
            )
        ],
    )

    assert [item.message for item in dashboard.recent_activity[:2]] == [
        "Outreach for Example Sponsor approved",
        "Outreach for Example Sponsor reviewed",
    ]
    assert dashboard.recent_activity[0].occurred_at > (
        dashboard.recent_activity[1].occurred_at
    )


def test_unreliable_recent_activity_is_omitted():
    dashboard = build(
        intelligence=SimpleNamespace(sponsor_eligibility=intelligence().sponsor_eligibility),
        assets=[],
        prospects=[],
        opportunities=[],
    )

    assert dashboard.recent_activity == ()


def test_continue_working_contains_only_unlocked_destinations():
    dashboard = build()

    assert [link.label for link in dashboard.continue_links] == [
        "View Strategy",
    ]


def test_strategy_working_has_explicit_resume_action():
    dashboard = build(generation_job=SimpleNamespace(status="processing"))
    assert dashboard.top_priority.action.label == "View Strategy Progress"
    assert dashboard.top_priority.action.endpoint == "workspace"


def test_contact_research_progress_and_failure_link_to_exact_opportunity():
    working = build(opportunities=[opportunity(
        stage="Research Approved",
        contact_research_job=SimpleNamespace(status="processing"),
    )])
    failed = build(opportunities=[opportunity(
        stage="Research Approved",
        contact_research_job=SimpleNamespace(status="failed"),
    )])
    assert working.top_priority.action.label == "View Contact Research Progress"
    assert working.top_priority.action.route_params == {"opportunity_id": 1}
    assert failed.top_priority.action.label == "Try Contact Discovery Again"
    assert failed.top_priority.action.route_params == {"opportunity_id": 1}
    assert working.top_priority.supporting_line == (
        "Sponsor Opportunity: Example Sponsor"
    )
    assert failed.top_priority.supporting_line == (
        "Sponsor Opportunity: Example Sponsor"
    )
    assert "existing contact information were preserved" in (
        failed.top_priority.message
    )


@pytest.mark.parametrize("closed_stage", ["Lost", "Won"])
def test_closed_contact_failure_is_excluded_from_active_dashboard(closed_stage):
    closed = opportunity(
        identifier=41,
        stage=closed_stage,
        contact_research_job=SimpleNamespace(status="failed"),
        recommended_target="Closed Sponsor",
    )

    dashboard = build(opportunities=[closed])

    assert dashboard.top_priority.action.route_params != {"opportunity_id": 41}
    assert all(
        item.action.route_params.get("opportunity_id") != 41
        for item in dashboard.needs_attention
    )
    assert all("Closed Sponsor" not in worker.message for worker in dashboard.ai_team)
    assert all("Closed Sponsor" not in link.label for link in dashboard.continue_links)


def test_open_contact_failure_remains_actionable_and_record_specific():
    dashboard = build(opportunities=[opportunity(
        identifier=42,
        stage="Research Approved",
        contact_research_job=SimpleNamespace(status="failed"),
        recommended_target="Open Sponsor",
    )])

    assert dashboard.top_priority.action.label == "Try Contact Discovery Again"
    assert dashboard.top_priority.action.route_params == {"opportunity_id": 42}
    assert dashboard.top_priority.supporting_line == (
        "Sponsor Opportunity: Open Sponsor"
    )


def test_open_action_outranks_closed_failure_and_matches_ai_team():
    closed = opportunity(
        identifier=41,
        stage="Lost",
        contact_research_job=SimpleNamespace(status="failed"),
        recommended_target="Closed Sponsor",
        created_at=NOW - timedelta(days=2),
    )
    active = opportunity(
        identifier=42,
        stage="Research Approved",
        email="contact@active.example",
        recommended_target="Active Sponsor",
    )

    dashboard = build(opportunities=[closed, active])
    outreach_worker = next(
        worker for worker in dashboard.ai_team
        if worker.name == "Outreach Worker"
    )

    assert dashboard.top_priority.action.label == "Generate Outreach"
    assert dashboard.top_priority.action.route_params == {"opportunity_id": 42}
    assert dashboard.top_priority.supporting_line == (
        "Sponsor Opportunity: Active Sponsor"
    )
    assert outreach_worker.detail == "Active Sponsor"
    assert "Closed Sponsor" not in outreach_worker.message
    assert any(
        item.action.route_params == {"opportunity_id": 41}
        for item in dashboard.recent_activity
    )


def test_all_active_job_types_on_closed_opportunity_are_not_resumable():
    closed = opportunity(
        identifier=43,
        stage="Won",
        contact_research_job=SimpleNamespace(status="processing"),
        outreach_generation_job=SimpleNamespace(status="working"),
        follow_up_generation_job=SimpleNamespace(status="queued"),
        recommended_target="Completed Sponsor",
    )

    dashboard = build(opportunities=[closed])

    assert dashboard.top_priority.action.route_params != {"opportunity_id": 43}
    assert all(
        item.action.route_params.get("opportunity_id") != 43
        for item in dashboard.needs_attention
    )
    assert all("Completed Sponsor" not in worker.message for worker in dashboard.ai_team)


def test_outreach_worker_states_resume_exact_opportunity():
    working = build(opportunities=[opportunity(
        outreach_generation_job=SimpleNamespace(status="working"),
    )])
    failed = build(opportunities=[opportunity(
        outreach_generation_job=SimpleNamespace(status="failed"),
    )])
    assert working.top_priority.action.label == "View Outreach Progress"
    assert failed.top_priority.action.label == "Try Outreach Again"
    assert working.top_priority.action.route_params == {"opportunity_id": 1}
    assert failed.top_priority.action.route_params == {"opportunity_id": 1}
    assert working.top_priority.supporting_line == (
        "Sponsor Opportunity: Example Sponsor"
    )
    assert failed.top_priority.supporting_line == (
        "Sponsor Opportunity: Example Sponsor"
    )
    assert "review, approval, and delivery information were preserved" in (
        failed.top_priority.message
    )


def test_follow_up_resume_states_link_to_exact_opportunity():
    working = build(opportunities=[opportunity(
        stage="Sent",
        follow_up_generation_job=SimpleNamespace(status="working"),
    )])
    failed = build(opportunities=[opportunity(
        stage="Sent",
        follow_up_generation_job=SimpleNamespace(status="failed"),
    )])
    review = build(opportunities=[opportunity(
        stage="Sent", follow_up_message="Draft follow-up",
    )])
    send = build(opportunities=[opportunity(
        stage="Sent", follow_up_message="Reviewed follow-up",
        follow_up_reviewed_at=NOW,
    )])
    assert working.top_priority.action.label == "View Follow-Up Progress"
    assert failed.top_priority.action.label == "Try Follow-Up Again"
    assert "prior follow-up history were preserved" in (
        failed.top_priority.message
    )
    assert review.top_priority.action.label == "Review Follow-Up"
    assert send.top_priority.action.label == "Send Follow-Up"
    assert {
        item.top_priority.action.route_params["opportunity_id"]
        for item in (working, failed, review, send)
    } == {1}
    assert all(
        item.top_priority.supporting_line
        == "Sponsor Opportunity: Example Sponsor"
        for item in (working, failed, review, send)
    )


def test_opportunity_name_is_consistent_in_priority_and_ai_team():
    dashboard = build(opportunities=[opportunity(outreach="Draft")])
    outreach_worker = next(
        worker
        for worker in dashboard.ai_team
        if worker.name == "Outreach Worker"
    )

    assert dashboard.top_priority.supporting_line == (
        "Sponsor Opportunity: Example Sponsor"
    )
    assert outreach_worker.detail_label == "Sponsor Opportunity"
    assert outreach_worker.detail == "Example Sponsor"


def test_equal_priority_uses_oldest_waiting_then_lowest_id():
    newer = opportunity(identifier=9, updated_at=NOW, created_at=NOW)
    older_high_id = opportunity(
        identifier=8, updated_at=NOW - timedelta(hours=1),
        created_at=NOW - timedelta(hours=1),
    )
    older_low_id = opportunity(
        identifier=3, updated_at=NOW - timedelta(hours=1),
        created_at=NOW - timedelta(hours=1),
    )
    for item in (newer, older_high_id, older_low_id):
        item.outreach = "Draft"
    dashboard = build(opportunities=[newer, older_high_id, older_low_id])
    assert dashboard.top_priority.action.route_params == {"opportunity_id": 3}


def test_top_priority_destination_is_not_duplicated_elsewhere():
    dashboard = build(research_assignments=[assignment("working")])
    top = dashboard.top_priority.action
    assert all(
        (item.action.endpoint, item.action.route_params)
        != (top.endpoint, top.route_params)
        for item in dashboard.needs_attention
    )
    assert all(link.endpoint != top.endpoint for link in dashboard.continue_links)


def test_successful_research_retry_supersedes_historical_failure_for_asset():
    dashboard = build(research_assignments=[
        assignment("needs_attention", identifier=1, asset_id=7),
        assignment("completed", identifier=4, asset_id=7),
    ])
    assert dashboard.top_priority.action.label == "Review Sponsor Results"
    assert dashboard.top_priority.action.route_params == {"assignment_id": 4}
    assert all(
        item.action.route_params.get("assignment_id") != 1
        for item in dashboard.needs_attention
    )


def test_successful_opportunity_data_supersedes_obsolete_job_failures():
    contact = opportunity(
        identifier=1,
        stage="Research Approved",
        email="partnerships@example.org",
        contact_research_job=SimpleNamespace(status="failed"),
    )
    outreach = opportunity(
        identifier=2,
        stage="Ready to Send",
        outreach="Persisted outreach",
        outreach_generation_job=SimpleNamespace(status="failed"),
    )
    follow_up = opportunity(
        identifier=3,
        stage="Sent",
        follow_up_date=NOW.date() - timedelta(days=1),
        follow_up_message="Persisted follow-up",
        follow_up_generation_job=SimpleNamespace(status="failed"),
    )

    dashboard = build(opportunities=[contact, outreach, follow_up])

    assert dashboard.top_priority.title == "Review Follow-Up"
    assert dashboard.top_priority.action.route_params == {
        "opportunity_id": 3
    }
    assert all(
        not item.title.endswith("generation needs attention")
        for item in dashboard.needs_attention
    )


def test_active_follow_up_supersedes_older_persisted_draft_state():
    dashboard = build(opportunities=[opportunity(
        stage="Sent",
        follow_up_date=NOW.date() - timedelta(days=1),
        follow_up_message="Older persisted follow-up",
        follow_up_generation_job=SimpleNamespace(status="queued"),
    )])

    assert dashboard.top_priority.status == "Working"
    assert dashboard.top_priority.title == "Your Follow-Up Worker is working."
    assert dashboard.top_priority.action.route_params == {
        "opportunity_id": 1
    }


def test_active_outreach_supersedes_older_persisted_review_state():
    dashboard = build(opportunities=[opportunity(
        stage="Ready to Send",
        outreach="Older persisted outreach",
        outreach_generation_job=SimpleNamespace(status="queued"),
    )])

    assert dashboard.top_priority.status == "Working"
    assert dashboard.top_priority.title == "Your Outreach Worker is working."


@pytest.mark.parametrize("status", ["pending", "processing"])
def test_strategy_active_states_use_approved_working_copy(status):
    dashboard = build(generation_job=SimpleNamespace(status=status))
    assert dashboard.top_priority.title == "Your Strategy Worker is working."
    assert dashboard.top_priority.message == (
        "Please wait while Marsha AI builds your sponsorship strategy."
    )


@pytest.mark.parametrize("status", ["ready", "working"])
def test_research_active_states_use_approved_working_copy(status):
    dashboard = build(research_assignments=[assignment(status)])
    assert dashboard.top_priority.title == "Your Research Worker is working."
    assert dashboard.top_priority.message == (
        "Please wait while Marsha AI searches for and evaluates sponsor opportunities."
    )


@pytest.mark.parametrize("status", ["queued", "processing"])
def test_contact_active_states_use_approved_working_copy(status):
    dashboard = build(opportunities=[opportunity(
        stage="Research Approved",
        contact_research_job=SimpleNamespace(status=status),
    )])
    assert dashboard.top_priority.worker_name == "Contact Discovery Worker"
    assert dashboard.top_priority.title == (
        "Your Contact Discovery Worker is working."
    )
    assert dashboard.top_priority.message == (
        "Please wait while Marsha AI looks for a verified contact route."
    )
    assert dashboard.top_priority.action.route_params == {
        "opportunity_id": 1
    }

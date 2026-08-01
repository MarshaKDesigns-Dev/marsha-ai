from datetime import date, datetime
from types import SimpleNamespace

from app import app
from services.workflow_navigation import (
    build_opportunity_progress,
    build_primary_navigation,
)


def item(**overrides):
    values = {
        "name": "Community Program",
        "strategy_meeting_completed_at": None,
        "is_active": True,
        "approval_status": "Pending",
        "stage": "Research Approved",
        "outreach": None,
        "reviewed_message": None,
        "message_reviewed_at": None,
        "message_approved_at": None,
        "sent_date": None,
        "follow_up_date": None,
        "follow_up_completed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def states(navigation):
    return {entry.key: entry.state for entry in navigation}


def test_setup_only_navigation_locks_later_workflow_stages():
    navigation = build_primary_navigation()

    assert states(navigation) == {
        "setup": "current",
        "strategy": "locked",
        "research": "locked",
        "pipeline": "locked",
    }


def test_strategy_is_current_after_setup_and_before_approval():
    navigation = build_primary_navigation(
        organization=item(name="Organization"),
        initiative=item(name="Initiative"),
    )

    assert states(navigation) == {
        "setup": "complete",
        "strategy": "current",
        "research": "locked",
        "pipeline": "locked",
    }


def test_research_is_current_after_approved_strategy():
    navigation = build_primary_navigation(
        organization=item(name="Organization"),
        initiative=item(
            name="Initiative",
            strategy_meeting_completed_at=datetime(2026, 7, 30),
        ),
        intelligence=item(),
        assets=[item(approval_status="Approved")],
    )

    assert states(navigation) == {
        "setup": "complete",
        "strategy": "complete",
        "research": "current",
        "pipeline": "locked",
    }
    assert next(item for item in navigation if item.key == "strategy").endpoint == (
        "strategy_work"
    )


def test_generated_unapproved_strategy_navigation_opens_strategy_view():
    navigation = build_primary_navigation(
        organization=item(name="Organization"),
        initiative=item(
            name="Initiative",
            strategy_meeting_completed_at=datetime(2026, 7, 30),
        ),
        intelligence=item(),
        assets=[item(approval_status="Pending")],
    )

    strategy = next(entry for entry in navigation if entry.key == "strategy")
    assert strategy.endpoint == "strategy_work"
    assert strategy.state == "current"


def test_pipeline_is_current_when_saved_opportunity_needs_action():
    navigation = build_primary_navigation(
        organization=item(name="Organization"),
        initiative=item(
            name="Initiative",
            strategy_meeting_completed_at=datetime(2026, 7, 30),
        ),
        intelligence=item(),
        assets=[item(approval_status="Approved")],
        opportunities=[item(stage="Ready to Send", outreach="Draft")],
    )

    assert states(navigation) == {
        "setup": "complete",
        "strategy": "complete",
        "research": "complete",
        "pipeline": "current",
    }


def test_research_returns_to_current_when_pipeline_has_no_waiting_work():
    navigation = build_primary_navigation(
        organization=item(name="Organization"),
        initiative=item(
            name="Initiative",
            strategy_meeting_completed_at=datetime(2026, 7, 30),
        ),
        intelligence=item(),
        assets=[item(approval_status="Approved")],
        opportunities=[item(stage="Won")],
    )

    assert states(navigation)["research"] == "current"
    assert states(navigation)["pipeline"] == "available"


def test_future_follow_up_does_not_make_pipeline_current():
    navigation = build_primary_navigation(
        organization=item(name="Organization"),
        initiative=item(
            name="Initiative",
            strategy_meeting_completed_at=datetime(2026, 7, 30),
        ),
        intelligence=item(),
        assets=[item(approval_status="Approved")],
        opportunities=[
            item(
                stage="Sent",
                sent_date=date(2026, 7, 30),
                follow_up_date=date(2026, 8, 6),
            )
        ],
        today=date(2026, 7, 30),
    )

    assert states(navigation)["research"] == "current"
    assert states(navigation)["pipeline"] == "available"


def test_opportunity_progress_tracks_review_approval_and_delivery():
    reviewed = build_opportunity_progress(
        item(
            stage="Ready to Send",
            outreach="Draft",
            message_reviewed_at=datetime(2026, 7, 30),
        )
    )
    approved = build_opportunity_progress(
        item(
            stage="Ready to Send",
            outreach="Draft",
            message_reviewed_at=datetime(2026, 7, 30),
            message_approved_at=datetime(2026, 7, 30),
        )
    )
    delivered = build_opportunity_progress(
        item(
            stage="Sent",
            outreach="Draft",
            message_reviewed_at=datetime(2026, 7, 30),
            message_approved_at=datetime(2026, 7, 30),
            sent_date=date(2026, 7, 30),
            follow_up_date=date(2026, 8, 6),
        )
    )

    assert states(reviewed)["review"] == "current"
    assert states(approved)["ready"] == "current"
    assert states(delivered)["follow_up"] == "current"


def test_completed_opportunity_marks_all_milestones_complete():
    progress = build_opportunity_progress(
        item(
            stage="Won",
            outreach="Draft",
            message_reviewed_at=datetime(2026, 7, 30),
            message_approved_at=datetime(2026, 7, 30),
            sent_date=date(2026, 7, 30),
            follow_up_completed_at=datetime(2026, 7, 30),
        )
    )

    assert [step.state for step in progress] == [
        "complete",
        "complete",
        "complete",
        "complete",
        "complete",
        "current",
    ]


def test_locked_navigation_renders_without_link_and_with_accessible_reason():
    template = app.jinja_env.get_template("_workflow_navigation.html")
    with app.test_request_context("/setup"):
        html = template.module.render_workflow_navigation(
            build_primary_navigation(),
            "setup",
        )

    assert 'aria-disabled="true"' in html
    assert "Complete Organization Setup to unlock this stage." in html
    assert 'href="/strategy_meeting"' not in html
    assert "state-current" in html
    assert "Locked" in html


def test_navigation_and_progress_markup_are_mobile_safe_and_centralized():
    base = app.jinja_loader.get_source(app.jinja_env, "base.html")[0]
    navigation = app.jinja_loader.get_source(
        app.jinja_env,
        "_workflow_navigation.html",
    )[0]
    opportunity = app.jinja_loader.get_source(
        app.jinja_env,
        "opportunity.html",
    )[0]

    assert "render_workflow_navigation(workflow_navigation, endpoint)" in base
    assert "overflow-wrap: anywhere" in open(
        "static/style.css",
        encoding="utf-8",
    ).read()
    assert "aria-current" in navigation
    assert "raw_status" not in navigation
    assert "render_opportunity_progress(opportunity_progress)" in opportunity

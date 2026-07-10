from types import SimpleNamespace

import app as app_module


def test_email_follow_up_gets_fallback_subject_when_ai_subject_is_empty(
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "get_org_profile",
        lambda: {"name": "Test Nonprofit"},
    )

    opportunity = SimpleNamespace(
        outreach_channel="email",
        recommended_target="Test Sponsor",
        parent_prospect="Parent Sponsor",
    )

    result = app_module.normalize_follow_up_draft(
        opportunity,
        {
            "subject": "   ",
            "message": "  Following up on our sponsorship request.  ",
        },
    )

    assert result["subject"] == (
        "Following up: Test Nonprofit and Test Sponsor"
    )
    assert result["message"] == (
        "Following up on our sponsorship request."
    )


def test_email_follow_up_preserves_ai_generated_subject(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_org_profile",
        lambda: {"name": "Test Nonprofit"},
    )

    opportunity = SimpleNamespace(
        outreach_channel="email",
        recommended_target="Test Sponsor",
        parent_prospect="Parent Sponsor",
    )

    result = app_module.normalize_follow_up_draft(
        opportunity,
        {
            "subject": "  Quick sponsorship follow-up  ",
            "message": "  Could we schedule a short conversation?  ",
        },
    )

    assert result["subject"] == "Quick sponsorship follow-up"
    assert result["message"] == (
        "Could we schedule a short conversation?"
    )


def test_phone_follow_up_does_not_receive_email_subject(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_org_profile",
        lambda: {"name": "Test Nonprofit"},
    )

    opportunity = SimpleNamespace(
        outreach_channel="phone",
        recommended_target="Test Sponsor",
        parent_prospect="Parent Sponsor",
    )

    result = app_module.normalize_follow_up_draft(
        opportunity,
        {
            "subject": "",
            "message": "  Phone follow-up script.  ",
        },
    )

    assert result["subject"] == ""
    assert result["message"] == "Phone follow-up script."

def test_apply_follow_up_draft_replaces_stale_draft_and_clears_review_state(
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "get_org_profile",
        lambda: {"name": "Test Nonprofit"},
    )

    previous_review_time = object()
    previous_completion_time = object()

    opportunity = SimpleNamespace(
        outreach_channel="email",
        recommended_target="Test Sponsor",
        parent_prospect="Parent Sponsor",
        follow_up_subject="Old subject",
        follow_up_message="Old message",
        follow_up_review_notes="Old review notes",
        follow_up_reviewed_at=previous_review_time,
        follow_up_completed_at=previous_completion_time,
    )

    result = app_module.apply_follow_up_draft(
        opportunity,
        {
            "subject": "New follow-up subject",
            "message": "New follow-up message",
        },
    )

    assert result == {
        "subject": "New follow-up subject",
        "message": "New follow-up message",
    }
    assert opportunity.follow_up_subject == "New follow-up subject"
    assert opportunity.follow_up_message == "New follow-up message"
    assert opportunity.follow_up_review_notes is None
    assert opportunity.follow_up_reviewed_at is None
    assert opportunity.follow_up_completed_at is None


def test_apply_follow_up_draft_repairs_stale_email_draft_without_subject(
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "get_org_profile",
        lambda: {"name": "Test Nonprofit"},
    )

    opportunity = SimpleNamespace(
        outreach_channel="email",
        recommended_target="Test Sponsor",
        parent_prospect="Parent Sponsor",
        follow_up_subject="",
        follow_up_message="Old message",
        follow_up_review_notes=None,
        follow_up_reviewed_at=None,
        follow_up_completed_at=None,
    )

    app_module.apply_follow_up_draft(
        opportunity,
        {
            "subject": "",
            "message": "Fresh follow-up message",
        },
    )

    assert opportunity.follow_up_subject == (
        "Following up: Test Nonprofit and Test Sponsor"
    )
    assert opportunity.follow_up_message == "Fresh follow-up message"


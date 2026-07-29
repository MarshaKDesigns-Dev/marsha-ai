from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import render_template

import app as app_module


def opportunity(**overrides):
    values = {
        "id": 16,
        "organization_id": 1,
        "initiative_id": 1,
        "parent_prospect": "Packaging Express",
        "recommended_target": "Packaging Express",
        "category": "Print Sponsor",
        "score": 90,
        "contact_name": "Packaging Express",
        "title": "Printing Services",
        "department": None,
        "email": "info@example.org",
        "phone": None,
        "contact_url": None,
        "linkedin_url": None,
        "why_this_contact": "Verified public contact.",
        "confidence": "high",
        "verified_date": "2026-07-29",
        "sources": [],
        "sources_json": "[]",
        "outreach": "Original outreach.",
        "outreach_channel": "email",
        "reviewed_message": None,
        "message_review_notes": None,
        "message_reviewed_at": None,
        "message_approved_at": None,
        "subject": "Sponsor partnership",
        "stage": "Ready to Send",
        "follow_up_date": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def install_query(monkeypatch, item):
    query = MagicMock()
    query.get_or_404.return_value = item
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(query=query),
    )
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())
    return query


def render_opportunity(item):
    review_notes = None
    if item.message_review_notes:
        review_notes = item.message_review_notes
    with app_module.app.test_request_context(f"/opportunity/{item.id}"):
        return render_template(
            "opportunity.html",
            opp=item,
            contact_research_job=None,
            stages=[],
            test_mode=True,
            test_email="test@example.org",
            default_subject=item.subject or "",
            display_message=item.reviewed_message or item.outreach or "",
            review_notes=review_notes,
            follow_up_due=False,
            follow_up_review_notes=None,
        )


def test_unreviewed_message_cannot_be_approved(monkeypatch):
    item = opportunity()
    install_query(monkeypatch, item)

    response = app_module.app.test_client().post(
        "/opportunity/16/approve-message"
    )

    assert response.status_code == 302
    assert item.message_approved_at is None
    app_module.db.session.commit.assert_not_called()


def test_reviewed_message_requires_approval_before_send_actions():
    rendered = render_opportunity(
        opportunity(
            reviewed_message="Reviewed outreach.",
            message_reviewed_at=datetime(2026, 7, 29, 12, 0),
        )
    )

    assert "Approve Message for Sending" in rendered
    assert "/opportunity/16/approve-message" in rendered
    assert "/opportunity/16/send-email" not in rendered
    assert "/opportunity/16/mark-sent" not in rendered


def test_approval_route_timestamps_existing_review_once(monkeypatch):
    item = opportunity(
        reviewed_message="Reviewed outreach.",
        message_reviewed_at=datetime(2026, 7, 29, 12, 0),
    )
    install_query(monkeypatch, item)

    first = app_module.app.test_client().post(
        "/opportunity/16/approve-message"
    )
    approved_at = item.message_approved_at
    second = app_module.app.test_client().post(
        "/opportunity/16/approve-message"
    )

    assert first.status_code == 302
    assert second.status_code == 302
    assert isinstance(approved_at, datetime)
    assert item.message_approved_at == approved_at
    app_module.db.session.commit.assert_called_once_with()


def test_approved_message_displays_existing_send_actions():
    rendered = render_opportunity(
        opportunity(
            reviewed_message="Reviewed outreach.",
            message_reviewed_at=datetime(2026, 7, 29, 12, 0),
            message_approved_at=datetime(2026, 7, 29, 12, 5),
        )
    )

    assert "Approved for sending." in rendered
    assert "/opportunity/16/send-email" in rendered
    assert "/opportunity/16/mark-sent" in rendered


def test_delivery_routes_reject_reviewed_but_unapproved_message(monkeypatch):
    item = opportunity(
        reviewed_message="Reviewed outreach.",
        message_reviewed_at=datetime(2026, 7, 29, 12, 0),
    )
    install_query(monkeypatch, item)

    email_response = app_module.app.test_client().post(
        "/opportunity/16/send-email"
    )
    external_response = app_module.app.test_client().post(
        "/opportunity/16/mark-sent"
    )

    assert email_response.status_code == 302
    assert external_response.status_code == 302
    assert item.stage == "Ready to Send"
    app_module.db.session.commit.assert_not_called()


def test_send_route_accepts_explicitly_approved_message(monkeypatch):
    item = opportunity(
        reviewed_message="Reviewed outreach.",
        message_reviewed_at=datetime(2026, 7, 29, 12, 0),
        message_approved_at=datetime(2026, 7, 29, 12, 5),
    )
    install_query(monkeypatch, item)
    monkeypatch.setattr(app_module, "SMTP_EMAIL", "sender@example.org")
    monkeypatch.setattr(app_module, "SMTP_APP_PASSWORD", "test-password")
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(app_module.smtplib, "SMTP_SSL", lambda *args: smtp)

    response = app_module.app.test_client().post(
        "/opportunity/16/send-email"
    )

    assert response.status_code == 302
    assert item.stage == "Sent"
    smtp.send_message.assert_called_once()
    app_module.db.session.commit.assert_called_once_with()


def test_review_and_reset_clear_prior_approval(monkeypatch):
    prior_approval = datetime(2026, 7, 29, 12, 5)
    item = opportunity(
        reviewed_message="Old reviewed outreach.",
        message_reviewed_at=datetime(2026, 7, 29, 12, 0),
        message_approved_at=prior_approval,
    )
    install_query(monkeypatch, item)
    monkeypatch.setattr(
        app_module,
        "review_message_quality",
        lambda *args: {
            "improved_subject": "Updated subject",
            "improved_message": "Updated reviewed outreach.",
            "review_notes": "Updated.",
            "risk_flags": [],
        },
    )

    app_module.app.test_client().post(
        "/opportunity/16/review-message",
        data={"subject": "Subject", "message": "Draft"},
    )
    assert item.message_approved_at is None

    item.message_approved_at = prior_approval
    app_module.app.test_client().post(
        "/opportunity/16/reset-message-review"
    )
    assert item.message_approved_at is None


def test_pipeline_actions_follow_review_and_approval_state():
    cases = (
        (opportunity(), "Review Message"),
        (
            opportunity(
                reviewed_message="Reviewed.",
                message_reviewed_at=datetime(2026, 7, 29, 12, 0),
            ),
            "Approve Message",
        ),
        (
            opportunity(
                reviewed_message="Reviewed.",
                message_reviewed_at=datetime(2026, 7, 29, 12, 0),
                message_approved_at=datetime(2026, 7, 29, 12, 5),
            ),
            "Send Outreach",
        ),
    )

    with app_module.app.test_request_context("/pipeline"):
        for item, label in cases:
            rendered = render_template(
                "pipeline.html",
                opportunities=[item],
                today=None,
            )
            assert label in rendered

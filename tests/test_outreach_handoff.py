from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import render_template

import app as app_module


def opportunity(**overrides):
    values = {
        "id": 33,
        "organization_id": 11,
        "initiative_id": 22,
        "sponsor_prospect_id": 44,
        "parent_prospect": "Example Sponsor",
        "recommended_target": "Example Sponsor",
        "category": "Community Partner",
        "score": 90,
        "contact_name": "Jordan Lee",
        "title": "Partnerships Director",
        "department": "Community Partnerships",
        "email": "jordan@example.org",
        "phone": None,
        "contact_url": "https://example.org/contact",
        "linkedin_url": None,
        "why_this_contact": "Verified partnerships contact.",
        "confidence": "High",
        "verified_date": "2026-07-29",
        "sources": ["https://example.org/contact"],
        "sources_json": '["https://example.org/contact"]',
        "outreach": None,
        "outreach_channel": None,
        "reviewed_message": None,
        "message_reviewed_at": None,
        "message_approved_at": None,
        "subject": None,
        "stage": "Research Approved",
        "follow_up_date": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def route_context(monkeypatch, item):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    query = MagicMock()
    query.filter_by.return_value.first_or_404.return_value = item
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(query=query),
    )
    monkeypatch.setattr(
        app_module.db.session,
        "get",
        MagicMock(
            return_value=SimpleNamespace(
                why_fits="Strong community alignment.",
                recommended_ask="Support the approved sponsorship asset.",
                why_recommended="Verified fit.",
            )
        ),
    )
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())
    monkeypatch.setattr(
        app_module,
        "get_org_profile",
        lambda: {"name": "Bright Futures"},
    )
    return query


def render_opportunity(item):
    with app_module.app.test_request_context(f"/opportunity/{item.id}"):
        return render_template(
            "opportunity.html",
            opp=item,
            contact_research_job=None,
            stages=[],
            test_mode=True,
            test_email="test@example.org",
            default_subject="",
            display_message=item.outreach or "",
            review_notes=None,
            follow_up_due=False,
            follow_up_review_notes=None,
        )


def test_research_approved_opportunity_with_contact_shows_generate_action():
    rendered = render_opportunity(opportunity())

    assert "Generate Sponsor Outreach" in rendered
    assert "/opportunity/33/generate-outreach" in rendered


def test_research_approved_opportunity_without_contact_hides_generate_action():
    rendered = render_opportunity(
        opportunity(email=None, phone=None, contact_url=None)
    )

    assert "Generate Sponsor Outreach" not in rendered


def test_generate_outreach_uses_existing_worker_and_populates_draft(monkeypatch):
    item = opportunity(message_approved_at="stale approval")
    query = route_context(monkeypatch, item)
    draft = MagicMock(return_value="Evidence-backed sponsor email.")
    monkeypatch.setattr(app_module, "draft_outreach", draft)

    response = app_module.app.test_client().post(
        "/opportunity/33/generate-outreach"
    )

    assert response.status_code == 302
    assert response.location.endswith("/opportunity/33")
    query.filter_by.assert_called_once_with(
        id=33,
        organization_id=11,
        initiative_id=22,
    )
    draft.assert_called_once()
    assert item.outreach == "Evidence-backed sponsor email."
    assert item.subject == "Potential partnership with Bright Futures"
    assert item.outreach_channel == "email"
    assert item.stage == "Ready to Send"
    assert item.message_approved_at is None
    app_module.db.session.commit.assert_called_once_with()


def test_existing_draft_is_not_generated_twice(monkeypatch):
    item = opportunity(outreach="Existing draft.", stage="Ready to Send")
    route_context(monkeypatch, item)
    draft = MagicMock()
    monkeypatch.setattr(app_module, "draft_outreach", draft)

    response = app_module.app.test_client().post(
        "/opportunity/33/generate-outreach"
    )

    assert response.status_code == 302
    draft.assert_not_called()
    app_module.db.session.commit.assert_not_called()


def test_generated_email_can_be_reviewed_and_sent_after_existing_approval():
    draft_rendered = render_opportunity(
        opportunity(
            outreach="Generated draft.",
            outreach_channel="email",
            stage="Ready to Send",
        )
    )

    assert "review-message" in draft_rendered
    assert "Run Message Quality Review" in draft_rendered
    assert "send-email" not in draft_rendered

    reviewed_rendered = render_opportunity(
        opportunity(
            outreach="Generated draft.",
            reviewed_message="Reviewed draft.",
            message_reviewed_at="2026-07-29T12:00:00",
            outreach_channel="email",
            stage="Ready to Send",
        )
    )
    assert "Approve Message for Sending" in reviewed_rendered
    assert "send-email" not in reviewed_rendered
    assert "mark-sent" not in reviewed_rendered

    approved_rendered = render_opportunity(
        opportunity(
            outreach="Generated draft.",
            reviewed_message="Reviewed draft.",
            message_reviewed_at="2026-07-29T12:00:00",
            message_approved_at="2026-07-29T12:05:00",
            outreach_channel="email",
            stage="Ready to Send",
        )
    )
    assert "send-email" in approved_rendered
    assert "mark-sent" in approved_rendered


def test_pipeline_shows_generate_outreach_for_eligible_opportunity():
    with app_module.app.test_request_context("/pipeline"):
        rendered = render_template(
            "pipeline.html",
            opportunities=[opportunity()],
            today=None,
        )

    assert "Generate Outreach" in rendered
    assert "/opportunity/33/generate-outreach" in rendered

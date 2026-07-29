from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import render_template
from werkzeug.exceptions import NotFound

import app as app_module


def route_context(monkeypatch, *, opportunity=None, active_job=None):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    opportunity = opportunity or SimpleNamespace(id=33)
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.first_or_404.return_value = (
        opportunity
    )
    job_query = MagicMock()
    job_query.filter_by.return_value.filter.return_value.order_by.return_value.first.return_value = (
        active_job
    )
    job_model = MagicMock()
    job_model.query = job_query
    job_model.status.in_.return_value = "active-status-filter"
    job_model.created_at.desc.return_value = "created-desc"
    job_model.id.desc.return_value = "id-desc"
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(query=opportunity_query),
    )
    monkeypatch.setattr(app_module, "ContactResearchJob", job_model)
    monkeypatch.setattr(app_module.db.session, "add", MagicMock())
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())
    return opportunity_query, job_model


def test_contact_research_route_creates_one_queued_job_and_redirects(
    monkeypatch,
):
    opportunity_query, job_model = route_context(monkeypatch)

    response = app_module.app.test_client().post(
        "/opportunity/33/research-contact"
    )

    assert response.status_code == 302
    assert response.location.endswith("/opportunity/33")
    opportunity_query.filter_by.assert_called_once_with(
        id=33,
        organization_id=11,
        initiative_id=22,
    )
    job_model.assert_called_once_with(opportunity_id=33, status="queued")
    app_module.db.session.add.assert_called_once_with(job_model.return_value)
    app_module.db.session.commit.assert_called_once_with()


def test_duplicate_contact_research_post_reuses_active_job(monkeypatch):
    route_context(
        monkeypatch,
        active_job=SimpleNamespace(id=44, status="queued"),
    )

    response = app_module.app.test_client().post(
        "/opportunity/33/research-contact"
    )

    assert response.status_code == 302
    app_module.ContactResearchJob.assert_not_called()
    app_module.db.session.add.assert_not_called()
    app_module.db.session.commit.assert_not_called()


def test_wrong_organization_cannot_enqueue_contact_research(monkeypatch):
    opportunity_query, job_model = route_context(monkeypatch)
    opportunity_query.filter_by.return_value.first_or_404.side_effect = NotFound()

    response = app_module.app.test_client().post(
        "/opportunity/33/research-contact"
    )

    assert response.status_code == 404
    opportunity_query.filter_by.assert_called_once_with(
        id=33,
        organization_id=11,
        initiative_id=22,
    )
    job_model.assert_not_called()
    app_module.db.session.add.assert_not_called()


def test_opportunity_template_shows_contact_research_control_and_latest_status():
    template = app_module.app.jinja_loader.get_source(
        app_module.app.jinja_env,
        "opportunity.html",
    )[0]

    assert "Contact Research Needed" in template
    assert "Research Contact" in template
    assert "contact_research_job.status" in template
    assert "enqueue_contact_research" in template


def test_failed_contact_research_job_displays_failed():
    opportunity = SimpleNamespace(
        id=33,
        recommended_target="Example Sponsor",
        parent_prospect="Example Sponsor",
        contact_name=None,
        email=None,
        phone=None,
        contact_url=None,
    )
    with app_module.app.test_request_context("/opportunity/33"):
        rendered = render_template(
            "opportunity.html",
            opp=opportunity,
            contact_research_job=SimpleNamespace(status="failed"),
            stages=[],
            test_mode=True,
            test_email="test@example.org",
            default_subject="",
            display_message="",
            review_notes=None,
            follow_up_due=False,
            follow_up_review_notes=None,
        )

    assert "Failed" in rendered

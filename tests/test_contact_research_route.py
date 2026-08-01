from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import render_template
from werkzeug.exceptions import NotFound
import pytest

import app as app_module
import services.contact_research_worker as worker_module


def route_context(monkeypatch, *, opportunity=None):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    opportunity = opportunity or SimpleNamespace(id=33)
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.first_or_404.return_value = (
        opportunity
    )
    enqueue = MagicMock()
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
    monkeypatch.setattr(
        worker_module, "enqueue_contact_research_job", enqueue
    )
    return opportunity_query, enqueue


def test_contact_research_route_creates_one_queued_job_and_redirects(
    monkeypatch,
):
    opportunity_query, enqueue = route_context(monkeypatch)

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
    enqueue.assert_called_once()
    assert enqueue.call_args.args[0].id == 33


def test_duplicate_contact_research_post_reuses_active_job(monkeypatch):
    _, enqueue = route_context(monkeypatch)
    enqueue.return_value = (SimpleNamespace(id=44, status="queued"), False)

    response = app_module.app.test_client().post(
        "/opportunity/33/research-contact"
    )

    assert response.status_code == 302
    enqueue.assert_called_once()


def test_wrong_organization_cannot_enqueue_contact_research(monkeypatch):
    opportunity_query, enqueue = route_context(monkeypatch)
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
    enqueue.assert_not_called()


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

    assert "NEEDS ATTENTION" in rendered
    assert "Your Contact Discovery Worker needs your attention." in rendered
    assert "Try Contact Discovery Again" in rendered


@pytest.mark.parametrize(
    ("job_name", "title", "message"),
    [
        (
            "outreach_generation_job",
            "Your Outreach Worker is working.",
            "Please wait while Marsha AI prepares the sponsor message.",
        ),
        (
            "follow_up_generation_job",
            "Your Follow-Up Worker is working.",
            "Please wait while Marsha AI prepares the follow-up message.",
        ),
    ],
)
@pytest.mark.parametrize("status", ["queued", "working"])
def test_active_generation_uses_approved_language(
    job_name, title, message, status
):
    opportunity = SimpleNamespace(
        id=33, recommended_target="Example Sponsor",
        parent_prospect="Example Sponsor", contact_name="Jordan",
        email="jordan@example.org", phone=None, contact_url=None,
        outreach=None, reviewed_message=None, follow_up_message=None,
        stage="Research Approved",
    )
    context = {
        "opp": opportunity, "contact_research_job": None,
        "outreach_generation_job": None, "follow_up_generation_job": None,
        "stages": [], "test_mode": True, "test_email": "test@example.org",
        "default_subject": "", "display_message": "", "review_notes": None,
        "follow_up_due": False, "follow_up_review_notes": None,
    }
    context[job_name] = SimpleNamespace(status=status)
    with app_module.app.test_request_context("/opportunity/33"):
        rendered = render_template("opportunity.html", **context)

    assert title in rendered
    assert message in rendered
    assert "Your work will continue in the background." in rendered
    assert " is queued" not in rendered


def test_research_failure_hides_internal_error_and_explains_preservation():
    assignment = SimpleNamespace(
        id=71,
        status="needs_attention",
        error_details="RuntimeError: provider secret failure",
    )
    asset = SimpleNamespace(id=18, name="Community activation")
    with app_module.app.test_request_context("/research/assignments/71"):
        rendered = render_template(
            "research_results.html",
            assignment=assignment,
            asset=asset,
            results=[],
            saved_results={},
        )

    assert "Your Research Worker needs your attention." in rendered
    assert "earlier research, saved sponsors, and pipeline records were preserved" in rendered
    assert "Try This Assignment Again" in rendered
    assert "RuntimeError" not in rendered
    assert "provider secret failure" not in rendered


def test_new_follow_up_cycle_hides_completed_cycle_actions():
    opportunity = SimpleNamespace(
        id=33, recommended_target="Example Sponsor",
        parent_prospect="Example Sponsor", contact_name="Jordan",
        email="jordan@example.org", phone=None, contact_url=None,
        outreach="Original outreach", reviewed_message="Reviewed outreach",
        follow_up_message="Previously completed follow-up",
        follow_up_reviewed_at="2026-07-31",
        follow_up_completed_at="2026-08-01",
        follow_up_date="2026-08-08", stage="Sent",
        outreach_channel="email", sent_date="2026-07-20",
    )
    with app_module.app.test_request_context("/opportunity/33"):
        rendered = render_template(
            "opportunity.html", opp=opportunity,
            contact_research_job=None, outreach_generation_job=None,
            follow_up_generation_job=None, stages=[], test_mode=True,
            test_email="test@example.org", default_subject="",
            display_message="Original outreach", review_notes=None,
            follow_up_due=True, follow_up_review_notes=None,
        )

    assert "The next sponsor follow-up is due" in rendered
    assert "Generate New Follow-Up" in rendered
    assert "Regenerate Follow-Up" not in rendered
    assert "Complete Follow-Up" not in rendered

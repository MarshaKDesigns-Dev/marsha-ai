from types import SimpleNamespace
from unittest.mock import MagicMock

import app as app_module
import pytest
from services.sponsor_eligibility_gate import (
    CategoryResearchDecision,
)


def test_generation_route_enqueues_without_synchronous_generation(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=1)
    calls = []
    job = SimpleNamespace(status="pending", worker_id=None, attempt_count=0)

    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )

    def enqueue(org, init, *, regenerate=False):
        calls.append((org.id, init.id, regenerate))
        return job, True

    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        enqueue,
    )
    synchronous_generation = MagicMock()
    monkeypatch.setattr(
        app_module,
        "run_workspace_intelligence_generation",
        synchronous_generation,
    )

    with app_module.app.test_request_context(
        "/workspace/generate-intelligence",
        method="POST",
    ):
        response = (
            app_module.generate_workspace_sponsorship_intelligence()
        )

    assert calls == [(1, 10, False)]
    assert response.status_code == 302
    assert response.location.endswith("/workspace")
    synchronous_generation.assert_not_called()
    assert job.status == "pending"
    assert job.worker_id is None
    assert job.attempt_count == 0


def test_generation_route_passes_explicit_regenerate(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=1)
    calls = []

    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )

    def enqueue(org, init, *, regenerate=False):
        calls.append((org.id, init.id, regenerate))
        return SimpleNamespace(status="pending"), True

    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        enqueue,
    )

    with app_module.app.test_request_context(
        "/workspace/generate-intelligence",
        method="POST",
        data={"regenerate": "true"},
    ):
        app_module.generate_workspace_sponsorship_intelligence()

    assert calls == [(1, 10, True)]


def test_duplicate_generation_route_flashes_already_in_progress(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=1)

    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        lambda *args, **kwargs: (
            SimpleNamespace(status="processing"),
            False,
        ),
    )

    with app_module.app.test_request_context(
        "/workspace/generate-intelligence",
        method="POST",
    ):
        response = (
            app_module.generate_workspace_sponsorship_intelligence()
        )
        flashed = app_module.session.get("_flashes")

    assert response.status_code == 302
    assert flashed == [
        (
            "warning",
                "Strategy generation is already in progress.",
        )
    ]


def test_generation_route_rejects_ownership_mismatch(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=99)
    enqueue_calls = []

    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        lambda *args, **kwargs: enqueue_calls.append(args),
    )

    with app_module.app.test_request_context(
        "/workspace/generate-intelligence",
        method="POST",
    ):
        response = app_module.generate_workspace_sponsorship_intelligence()
        flashed = app_module.session.get("_flashes")

    assert response.status_code == 302
    assert flashed == [
        (
            "warning",
            "The sponsorship initiative does not belong to the organization.",
        )
    ]
    assert enqueue_calls == []


def test_generation_started_message_renders_after_redirect(monkeypatch):
    organization = SimpleNamespace(
        id=1,
        name="Community Arts Center",
        location="Durham, NC",
        sender_name="Jordan Lee",
        organization_type="Arts organization",
    )
    initiative = SimpleNamespace(
        id=10,
        organization_id=1,
        name="Summer Arts Festival",
        fundraising_target="Not set",
        deadline=None,
    )
    started_message = (
        "Your Strategy Worker has started. You can leave this page while "
        "the strategy is prepared."
    )

    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        lambda *args, **kwargs: (
            SimpleNamespace(status="pending"),
            True,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "get_org_profile",
        lambda: {"name": organization.name},
    )
    monkeypatch.setattr(
        app_module,
        "get_initiative_profile",
        lambda: {
            "target": "Not set",
            "deadline": "Not set",
            "audience": "Families",
            "needs": "Sponsors",
            "goals": "Expand programming",
        },
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda org, init: None,
    )
    monkeypatch.setattr(
        app_module,
        "get_workspace_intelligence_job",
        lambda org, init: SimpleNamespace(status="pending", message=None),
    )
    prospect_query = MagicMock()
    prospect_query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module,
        "SponsorProspect",
        SimpleNamespace(
            query=prospect_query,
            updated_at=SimpleNamespace(desc=lambda: "updated"),
            id=SimpleNamespace(desc=lambda: "id"),
        ),
    )
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(
            query=opportunity_query,
            updated_at=SimpleNamespace(desc=lambda: "updated"),
        ),
    )
    assignment_query = MagicMock()
    assignment_query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module,
        "ResearchAssignment",
        SimpleNamespace(
            query=assignment_query,
            created_at=SimpleNamespace(desc=lambda: "created"),
            id=SimpleNamespace(desc=lambda: "id"),
        ),
    )

    client = app_module.app.test_client()
    response = client.post("/workspace/generate-intelligence")

    assert response.status_code == 302
    assert response.location.endswith("/workspace")
    with client.session_transaction() as browser_session:
        assert ("success", started_message) in browser_session["_flashes"]


def test_workspace_builds_dashboard_from_existing_records(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=1)
    intelligence = SimpleNamespace(id=99)
    generation_job = SimpleNamespace(status="processing")
    categories = [SimpleNamespace(slug="community")]
    prospects = [SimpleNamespace(id=20)]
    opportunities = [SimpleNamespace(id=30)]
    dashboard = SimpleNamespace(greeting="Good morning, there")
    rendered = {}
    build_arguments = {}

    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )
    monkeypatch.setattr(
        app_module,
        "get_initiative_profile",
        lambda: {"initiative": "Example Initiative"},
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda org, init: intelligence,
    )
    monkeypatch.setattr(
        app_module,
        "get_workspace_intelligence_job",
        lambda org, init: generation_job,
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsor_categories",
        lambda org, init: categories,
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_assets",
        lambda org, init: [],
    )
    monkeypatch.setattr(
        app_module,
        "get_research_priorities",
        lambda org, init: (_ for _ in ()).throw(
            AssertionError("workspace must not load research priorities")
        ),
    )
    prospect_query = MagicMock()
    prospect_query.filter_by.return_value.order_by.return_value.all.return_value = prospects
    monkeypatch.setattr(
        app_module,
        "SponsorProspect",
        SimpleNamespace(
            query=prospect_query,
            updated_at=SimpleNamespace(desc=lambda: "updated"),
            id=SimpleNamespace(desc=lambda: "id"),
        ),
    )
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.order_by.return_value.all.return_value = opportunities
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(
            query=opportunity_query,
            updated_at=SimpleNamespace(desc=lambda: "updated"),
        ),
    )
    assignment_query = MagicMock()
    assignment_query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module,
        "ResearchAssignment",
        SimpleNamespace(
            query=assignment_query,
            created_at=SimpleNamespace(desc=lambda: "created"),
            id=SimpleNamespace(desc=lambda: "id"),
        ),
    )

    def build_dashboard(**kwargs):
        build_arguments.update(kwargs)
        return dashboard

    monkeypatch.setattr(app_module, "build_dashboard", build_dashboard)

    def render(template_name, **context):
        rendered.update(context)
        return template_name

    monkeypatch.setattr(app_module, "render_template", render)

    with app_module.app.test_request_context("/workspace"):
        response = app_module.workspace()

    assert response == "workspace.html"
    assert rendered == {
        "organization": organization,
        "initiative": initiative,
        "dashboard": dashboard,
    }
    assert build_arguments["organization"] is organization
    assert build_arguments["initiative"] is initiative
    assert build_arguments["intelligence"] is intelligence
    assert build_arguments["generation_job"] is generation_job
    assert build_arguments["top_category"] is categories[0]
    assert build_arguments["assets"] == []
    assert build_arguments["prospects"] is prospects
    assert build_arguments["opportunities"] is opportunities
    assert build_arguments["research_assignments"] == []
    prospect_query.filter_by.assert_called_once_with(
        organization_id=1,
        initiative_id=10,
        is_active=True,
    )
    opportunity_query.filter_by.assert_called_once_with(
        organization_id=1,
        initiative_id=10,
    )
    assignment_query.filter_by.assert_called_once_with(
        organization_id=1,
        initiative_id=10,
    )


@pytest.mark.parametrize(
    ("job_status", "terminal"),
    [
        ("pending", False),
        ("processing", False),
        ("completed", True),
        ("failed", True),
    ],
)
def test_workspace_status_reports_job_terminal_state(
    monkeypatch,
    job_status,
    terminal,
):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=2, organization_id=1)
    job = SimpleNamespace(status=job_status, message="Safe status message.")
    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )
    monkeypatch.setattr(
        app_module,
        "get_workspace_intelligence_job",
        lambda *args: job,
    )

    response = app_module.app.test_client().get("/workspace/status")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == job_status
    assert payload["terminal"] is terminal
    assert payload["refresh_url"] == "/workspace"
    if job_status == "failed":
        assert payload["message"] == (
            "Marsha AI could not complete the strategy update. Your previously "
            "saved strategy and setup information were preserved."
        )
        assert "Safe status message" not in payload["message"]


def test_workspace_status_redirects_polling_to_setup_without_records(
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: None,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: None,
    )

    response = app_module.app.test_client().get("/workspace/status")

    assert response.get_json() == {
        "status": "setup_required",
        "terminal": True,
        "refresh_url": "/setup",
    }


def test_workspace_template_is_dashboard_without_long_form_reports():
    template = open(
        "templates/workspace.html",
        encoding="utf-8",
    ).read()

    assert "SPONSORSHIP COORDINATOR" in template
    assert "dashboard.top_priority.worker_name" in template
    assert "dashboard.top_priority.worker_icon" in template
    assert "What Marsha AI is doing" in template
    assert "dashboard.ai_team" in template
    assert "setInterval(checkStatus, 5000)" in template
    assert "manual-status-refresh" in template
    assert "WORKFLOW" in template
    assert "Active initiative:" in template
    assert "RECENT ACTIVITY" in template
    assert "ORGANIZATION ANALYSIS" not in template
    assert "SPONSORSHIP STRATEGY" not in template
    assert "RECOMMENDED SPONSOR CATEGORIES" not in template
    assert "CURRENT SPONSORSHIP ASSETS" not in template
    assert "organization_analysis" not in template
    assert "sponsorship_strategy" not in template
    assert "categories" not in template
    assert "{% for asset" not in template

    assert "mission-control" in template
    assert "mission-worker-grid" in template
    assert "mission-detail-grid" in template


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/prospects/healthcare"),
        ("get", "/prospect/healthcare/0"),
        ("post", "/approve/healthcare/0"),
    ],
)
def test_direct_research_routes_enforce_server_side_gate(
    monkeypatch,
    method,
    path,
):
    monkeypatch.setattr(
        app_module,
        "get_category_research_decision",
        lambda category, **kwargs: CategoryResearchDecision(
            allowed=False,
            reason="Research is blocked by deterministic eligibility.",
            reason_code="blocked_for_test",
        ),
    )

    client = app_module.app.test_client()
    response = getattr(client, method)(path)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace")


def test_allowed_category_research_does_not_use_placeholder_prospects(
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "get_category_research_decision",
        lambda category, **kwargs: CategoryResearchDecision(allowed=True),
    )
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=2, organization_id=1)
    category_record = SimpleNamespace(
        slug="healthcare",
        category="Healthcare",
    )
    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_sponsor_category",
        lambda category: category_record,
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda org, init: SimpleNamespace(sponsor_eligibility=None),
    )
    query = MagicMock()
    query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module,
        "SponsorProspect",
        SimpleNamespace(
            query=query,
            ranking_score=SimpleNamespace(desc=lambda: "ranking"),
            company_name=SimpleNamespace(asc=lambda: "company"),
        ),
    )

    response = app_module.app.test_client().get("/prospects/healthcare")

    assert response.status_code == 200
    assert b"No credible sponsors saved yet." in response.data
    assert b"Duke Health" not in response.data

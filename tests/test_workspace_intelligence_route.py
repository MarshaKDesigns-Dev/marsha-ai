from types import SimpleNamespace

import app as app_module
import pytest
from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_eligibility_gate import (
    CategoryResearchDecision,
    evaluate_category_research,
)


def test_generation_route_enqueues_without_synchronous_generation(monkeypatch):
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
    monkeypatch.setattr(
        app_module,
        "run_workspace_intelligence_generation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("synchronous generation must not run")
        ),
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
            "Sponsorship intelligence generation is already in progress.",
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
    )
    initiative = SimpleNamespace(
        id=10,
        organization_id=1,
        name="Summer Arts Festival",
    )
    started_message = "Sponsorship intelligence generation started."

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
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(query=SimpleNamespace(all=lambda: [])),
    )

    client = app_module.app.test_client()
    response = client.post(
        "/workspace/generate-intelligence",
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.request.path == "/workspace"
    assert started_message in html
    assert 'class="alert alert-success"' in html
    assert "Sponsorship intelligence generation is queued." in html


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (
            "processing",
            None,
            "Sponsorship intelligence is being generated.",
        ),
        (
            "failed",
            "Safe generation failure.",
            "Safe generation failure.",
        ),
    ],
)
def test_workspace_renders_generation_job_status(status, message, expected):
    with app_module.app.test_request_context("/workspace"):
        html = app_module.render_template(
            "workspace.html",
            org={},
            organization=SimpleNamespace(
                name="Community Arts Center",
                location="Durham, NC",
            ),
            initiative=SimpleNamespace(name="Summer Arts Festival"),
            data={},
            intelligence=None,
            generation_job=SimpleNamespace(
                status=status,
                message=message,
            ),
            categories=[],
            assets=[],
            pipeline=[],
        )

    assert expected in html


def test_workspace_loads_all_persisted_intelligence(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=1)
    intelligence = SimpleNamespace(id=99)
    categories = [SimpleNamespace(slug="community")]
    assets = [SimpleNamespace(name="Community Partnership")]
    rendered = {}

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
        "get_org_profile",
        lambda: {"name": "Example Organization"},
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
        lambda org, init: SimpleNamespace(
            status="processing",
            message=None,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsor_categories",
        lambda org, init: categories,
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_assets",
        lambda org, init: assets,
    )
    monkeypatch.setattr(
        app_module,
        "get_research_priorities",
        lambda org, init: (_ for _ in ()).throw(
            AssertionError("workspace must not load research priorities")
        ),
    )
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(
            query=SimpleNamespace(all=lambda: []),
        ),
    )

    def render(template_name, **context):
        rendered.update(context)
        return template_name

    monkeypatch.setattr(app_module, "render_template", render)

    with app_module.app.test_request_context("/workspace"):
        response = app_module.workspace()

    assert response == "workspace.html"
    assert rendered["intelligence"] is intelligence
    assert rendered["categories"] is categories
    assert rendered["assets"] is assets
    assert "research_priorities" not in rendered
    assert rendered["generation_job"].status == "processing"
    assert rendered["intelligence"] is intelligence


def test_workspace_template_exposes_generated_intelligence():
    template = open(
        "templates/workspace.html",
        encoding="utf-8",
    ).read()

    assert "Generate Sponsorship Intelligence" in template
    assert "Regenerate Intelligence" in template
    assert "ORGANIZATION ANALYSIS" in template
    assert "SPONSORSHIP STRATEGY" in template
    assert "RECOMMENDED SPONSOR CATEGORIES" in template
    assert "CURRENT SPONSORSHIP ASSETS" in template
    assert "Where would you like to begin?" in template
    assert "Research This Category" in template
    assert "category=category.slug" in template
    assert "RESEARCH PRIORITIES" not in template
    assert "Sponsorship intelligence generation is queued." in template
    assert "Sponsorship intelligence is being generated." in template


def test_workspace_renders_persisted_eligibility_and_allowed_category():
    eligibility = SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support professional education.",
            location="Charlotte, NC",
            initiative_name="Leadership Conference",
            audience="Adults 21 and older",
        )
    )
    category = SimpleNamespace(
        slug="technology",
        category="Technology",
        score=90,
        fit="Strong alignment",
        ideal_sponsor_profile="Business technology providers",
        research_direction="Research regional providers",
    )

    with app_module.app.test_request_context("/workspace"):
        html = app_module.render_template(
            "workspace.html",
            org={},
            organization=SimpleNamespace(
                name="Leadership Association",
                location="Charlotte, NC",
            ),
            initiative=SimpleNamespace(name="Leadership Conference"),
            data={},
            intelligence=SimpleNamespace(
                organization_analysis={},
                sponsorship_strategy={},
                sponsor_eligibility=eligibility,
            ),
            generation_job=None,
            categories=[category],
            category_research_decisions={
                category.slug: evaluate_category_research(
                    eligibility,
                    category,
                )
            },
            assets=[],
            pipeline=[],
        )

    assert "SPONSOR ELIGIBILITY" in html
    assert "Sponsor research allowed:" in html
    assert "Yes" in html
    assert "sponsor-eligibility-v1" in html
    assert 'href="/prospects/technology"' in html


def test_workspace_renders_legacy_eligibility_warning():
    with app_module.app.test_request_context("/workspace"):
        html = app_module.render_template(
            "workspace.html",
            org={},
            organization=SimpleNamespace(name="Example", location=""),
            initiative=SimpleNamespace(name="Example Initiative"),
            data={},
            intelligence=SimpleNamespace(
                organization_analysis={},
                sponsorship_strategy={},
                sponsor_eligibility=None,
            ),
            generation_job=None,
            categories=[],
            category_research_decisions={},
            assets=[],
            pipeline=[],
        )

    assert "Sponsor eligibility analysis has not been generated." in html


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
        lambda category: CategoryResearchDecision(
            allowed=False,
            reason="Research is blocked by deterministic eligibility.",
            reason_code="blocked_for_test",
        ),
    )

    client = app_module.app.test_client()
    response = getattr(client, method)(path)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace")


def test_allowed_category_research_reaches_existing_prospect_page(
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "get_category_research_decision",
        lambda category: CategoryResearchDecision(allowed=True),
    )

    response = app_module.app.test_client().get("/prospects/healthcare")

    assert response.status_code == 200
    assert b"Duke Health" in response.data

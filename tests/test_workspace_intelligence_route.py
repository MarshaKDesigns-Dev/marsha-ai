from types import SimpleNamespace

import app as app_module
import pytest


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
            research_priorities=[],
            pipeline=[],
        )

    assert expected in html


def test_workspace_loads_all_persisted_intelligence(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=1)
    intelligence = SimpleNamespace(id=99)
    categories = [SimpleNamespace(slug="community")]
    assets = [SimpleNamespace(name="Community Partnership")]
    priorities = [SimpleNamespace(priority=1)]
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
        lambda org, init: priorities,
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
    assert rendered["research_priorities"] is priorities
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
    assert "PROSPECT RESEARCH QUEUE" in template
    assert "CURRENT SPONSORSHIP ASSETS" in template
    assert "RESEARCH PRIORITIES" in template
    assert "Sponsorship intelligence generation is queued." in template
    assert "Sponsorship intelligence is being generated." in template

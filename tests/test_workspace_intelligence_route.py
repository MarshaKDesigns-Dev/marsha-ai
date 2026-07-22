from types import SimpleNamespace

import app as app_module


def test_generation_route_calls_existing_application_service(monkeypatch):
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

    def generate(organization_id, initiative_id, *, regenerate=False):
        calls.append((organization_id, initiative_id, regenerate))
        return SimpleNamespace(
            success=True,
            message="Sponsorship intelligence was generated and saved.",
        )

    monkeypatch.setattr(
        app_module,
        "run_workspace_intelligence_generation",
        generate,
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

    def generate(organization_id, initiative_id, *, regenerate=False):
        calls.append((organization_id, initiative_id, regenerate))
        return SimpleNamespace(success=True, message="Regenerated.")

    monkeypatch.setattr(
        app_module,
        "run_workspace_intelligence_generation",
        generate,
    )

    with app_module.app.test_request_context(
        "/workspace/generate-intelligence",
        method="POST",
        data={"regenerate": "true"},
    ):
        app_module.generate_workspace_sponsorship_intelligence()

    assert calls == [(1, 10, True)]


def test_generation_route_returns_safe_service_error(monkeypatch):
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
        "run_workspace_intelligence_generation",
        lambda *args, **kwargs: SimpleNamespace(
            success=False,
            message=(
                "Sponsorship intelligence could not be generated. "
                "Please try again."
            ),
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
            "Sponsorship intelligence could not be generated. "
            "Please try again.",
        )
    ]


def test_generation_route_displays_timeout_message(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=10, organization_id=1)
    timeout_message = (
        "Sponsorship intelligence generation took too long. "
        "Please try again."
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
        "run_workspace_intelligence_generation",
        lambda *args, **kwargs: SimpleNamespace(
            success=False,
            message=timeout_message,
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
    assert response.location.endswith("/workspace")
    assert flashed == [("warning", timeout_message)]


def test_timeout_message_renders_after_redirect(monkeypatch):
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
    timeout_message = (
        "Sponsorship intelligence generation took too long. "
        "Please try again."
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
        "run_workspace_intelligence_generation",
        lambda *args, **kwargs: SimpleNamespace(
            success=False,
            message=timeout_message,
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
    assert timeout_message in html
    assert 'class="alert alert-warning"' in html


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

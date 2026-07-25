import app as app_module


def test_workspace_uses_database_backed_intelligence():
    source = open("app.py", encoding="utf-8").read()

    workspace_source = source.split('@app.route("/workspace")', 1)[1].split(
        '@app.route("/workspace/generate-intelligence"', 1
    )[0]

    assert "seed_sponsorship_intelligence(organization, initiative)" not in (
        workspace_source
    )
    assert "get_sponsorship_intelligence(" in workspace_source
    assert "get_sponsor_categories(organization, initiative)" in (
        workspace_source
    )
    assert "build_dashboard(" in workspace_source
    assert "SponsorProspect.query.filter_by(" in workspace_source
    assert "Opportunity.query.order_by(" in workspace_source
    assert "get_sponsorship_assets(organization, initiative)" not in (
        workspace_source
    )
    assert "get_research_priorities(organization, initiative)" not in (
        workspace_source
    )


def test_dynamic_models_exist():
    source = open("app.py", encoding="utf-8").read()

    assert "class SponsorCategory(db.Model):" in source
    assert "class SponsorshipAsset(db.Model):" in source

    assert "organization_id" in source
    assert "initiative_id" in source


def test_legacy_seed_is_not_used_by_workspace_route():
    source = open("app.py", encoding="utf-8").read()
    workspace_source = source.split('@app.route("/workspace")', 1)[1].split(
        '@app.route("/workspace/generate-intelligence"', 1
    )[0]

    assert "seed_sponsorship_intelligence(" not in workspace_source

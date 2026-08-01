import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import app as app_module


def _active_records():
    organization = SimpleNamespace(id=1, name="Community Group")
    initiative = SimpleNamespace(
        id=2,
        organization_id=1,
        name="Community Initiative",
        strategy_concerns_constraints="Limited staff capacity",
    )
    return organization, initiative


def _intelligence():
    strategy = {
        "positioning_statement": "A community-centered partnership strategy.",
        "strategic_theme": "Shared community impact",
        "recommended_approach": "Build partnerships around measurable value.",
        "objectives": [
            {
                "objective": "Fund access",
                "rationale": "The initiative prioritizes scholarships.",
            }
        ],
        "risks_or_constraints": ["Limited staff capacity"],
    }
    return SimpleNamespace(
        sponsorship_strategy=strategy,
        sponsorship_strategy_json=json.dumps(strategy),
    )


def _patch_context(monkeypatch, *, assets=None):
    organization, initiative = _active_records()
    intelligence = _intelligence()
    categories = [
        SimpleNamespace(
            category="Financial Services",
            fit="Aligned with financial access.",
        )
    ]
    resolved_assets = assets or [
        SimpleNamespace(
            name="Scholarship Partner",
            description="Support participant access.",
            sponsor_value="Visible community impact.",
            approval_status="Pending",
            approval_updated_at=None,
        )
    ]
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda *args: intelligence,
    )
    monkeypatch.setattr(
        app_module, "get_sponsor_categories", lambda *args: categories
    )
    monkeypatch.setattr(
        app_module, "get_sponsorship_assets", lambda *args: resolved_assets
    )
    return organization, initiative, resolved_assets


def test_strategy_work_renders_generated_content(monkeypatch):
    _patch_context(monkeypatch)

    response = app_module.app.test_client().get("/workspace/strategy")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "A community-centered partnership strategy." in html
    assert "Fund access" in html
    assert "Financial Services" in html
    assert "Scholarship Partner" in html
    assert "Limited staff capacity" in html
    assert html.count("Approve Strategy &amp; Continue") == 1
    assert "continue directly to Sponsor Research" in html
    assert "Edit Strategy Inputs" in html
    assert "Rebuild Strategy" in html
    assert 'name="regenerate" value="true"' in html
    assert "STRATEGIC DIRECTION" in html
    assert "DECISION PRIORITIES" in html
    assert "WHO TO PURSUE" in html
    assert "WHAT TO OFFER" in html


def test_approved_strategy_remains_viewable_with_secondary_actions(monkeypatch):
    approved_asset = SimpleNamespace(
        name="Scholarship Partner",
        description="Support participant access.",
        sponsor_value="Visible community impact.",
        approval_status="Approved",
        approval_updated_at=object(),
        is_active=True,
    )
    _patch_context(monkeypatch, assets=[approved_asset])

    response = app_module.app.test_client().get("/workspace/strategy")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Your Sponsorship Strategy" in html
    assert "Your Sponsorship Strategy is approved" in html
    assert "Return to Dashboard" in html
    assert "Edit Strategy Inputs" in html
    assert "Rebuild Strategy" in html
    assert "Approve Strategy &amp; Continue" not in html


def test_strategy_review_has_one_primary_decision_and_secondary_changes(monkeypatch):
    _patch_context(monkeypatch)

    html = app_module.app.test_client().get(
        "/workspace/strategy"
    ).get_data(as_text=True)

    assert html.count('action="/workspace/strategy/approve"') == 1
    assert html.count("Approve Strategy &amp; Continue") == 1
    assert html.index("Approve Strategy &amp; Continue") < html.index(
        "Edit Strategy Inputs"
    )
    assert "Need to make changes?" in html
    assert 'href="/strategy-meeting"' in html
    assert 'href="/workspace"' in html


def test_strategy_approval_approves_assets_and_opens_research(monkeypatch):
    _, _, assets = _patch_context(monkeypatch)
    commit = MagicMock()
    monkeypatch.setattr(app_module.db.session, "commit", commit)

    response = app_module.app.test_client().post(
        "/workspace/strategy/approve"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/research")
    assert assets[0].approval_status == "Approved"
    assert assets[0].approval_updated_at is not None
    commit.assert_called_once()


def test_strategy_approval_is_idempotent(monkeypatch):
    approved_at = object()
    asset = SimpleNamespace(
        name="Scholarship Partner",
        description="Support participant access.",
        sponsor_value="Visible community impact.",
        approval_status="Approved",
        approval_updated_at=approved_at,
    )
    _patch_context(monkeypatch, assets=[asset])
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())

    response = app_module.app.test_client().post(
        "/workspace/strategy/approve"
    )

    assert response.status_code == 302
    assert asset.approval_status == "Approved"
    assert asset.approval_updated_at is approved_at

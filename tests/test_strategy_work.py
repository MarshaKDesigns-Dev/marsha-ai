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
    assert "Approve Strategy and Continue" in html


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

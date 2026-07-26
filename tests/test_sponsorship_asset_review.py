from types import SimpleNamespace
from unittest.mock import MagicMock

import app as app_module


def _configure(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=2, organization_id=1)
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
    return organization, initiative


def test_asset_review_renders_pending_generated_assets(monkeypatch):
    organization, initiative = _configure(monkeypatch)
    asset = SimpleNamespace(
        id=3,
        name="Education Partner",
        description="Supports workshops",
        value="Community visibility",
        sponsor_value="Community visibility",
        capacity="2",
        approval_status="Pending",
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda *args: SimpleNamespace(id=4),
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_assets",
        lambda *args: [asset],
    )

    response = app_module.app.test_client().get("/workspace/assets")

    assert response.status_code == 200
    assert b"Education Partner" in response.data
    assert b"Pending" in response.data
    assert b"0 assets approved" in response.data
    assert b"Return to Dashboard" in response.data
    assert b"Each Approve or Reject action saves immediately" in response.data


def test_asset_review_enables_continuation_after_an_approval(monkeypatch):
    _configure(monkeypatch)
    approved = SimpleNamespace(
        id=3,
        name="Education Partner",
        description="Supports workshops",
        value="Community visibility",
        sponsor_value="Community visibility",
        capacity="2",
        approval_status="Approved",
        is_active=True,
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda *args: SimpleNamespace(id=4),
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_assets",
        lambda *args: [approved],
    )

    response = app_module.app.test_client().get("/workspace/assets")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "1 asset approved" in html
    assert 'href="/workspace"' in html
    assert "Continue to Sponsor Research" in html
    assert (
        '<a class="btn btn-primary btn-lg" href="/workspace">'
        in html
    )


def test_direct_status_string_cannot_bypass_controlled_actions(monkeypatch):
    _configure(monkeypatch)
    asset = SimpleNamespace(
        id=3,
        approval_status="Pending",
        approval_updated_at=None,
    )
    monkeypatch.setattr(
        app_module,
        "_active_sponsorship_asset",
        lambda asset_id: asset,
    )
    commit = MagicMock()
    monkeypatch.setattr(app_module.db.session, "commit", commit)

    response = app_module.app.test_client().post(
        "/workspace/assets/3",
        data={"action": "set-status", "approval_status": "Approved"},
    )

    assert response.status_code == 302
    assert asset.approval_status == "Pending"
    commit.assert_not_called()


def test_approve_and_reject_map_to_allowed_statuses(monkeypatch):
    _configure(monkeypatch)
    asset = SimpleNamespace(
        id=3,
        approval_status="Pending",
        approval_updated_at=None,
    )
    monkeypatch.setattr(
        app_module,
        "_active_sponsorship_asset",
        lambda asset_id: asset,
    )
    commit = MagicMock()
    monkeypatch.setattr(app_module.db.session, "commit", commit)
    client = app_module.app.test_client()

    client.post("/workspace/assets/3", data={"action": "approve"})
    assert asset.approval_status == "Approved"
    client.post("/workspace/assets/3", data={"action": "reject"})
    assert asset.approval_status == "Rejected"
    assert commit.call_count == 2


def test_custom_asset_is_pending_and_marked_custom(monkeypatch):
    organization, initiative = _configure(monkeypatch)
    added = []
    monkeypatch.setattr(
        app_module.db.session,
        "add",
        lambda value: added.append(value),
    )
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())

    response = app_module.app.test_client().post(
        "/workspace/assets",
        data={
            "name": "Workshop Partner",
            "sponsor_value": "Workshop recognition",
        },
    )

    assert response.status_code == 302
    assert added[0].approval_status == "Pending"
    assert added[0].source == "custom"
    assert added[0].organization_id == organization.id
    assert added[0].initiative_id == initiative.id

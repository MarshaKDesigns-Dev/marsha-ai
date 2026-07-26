from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import app as app_module


def _records():
    organization = SimpleNamespace(id=1, name="Community Group")
    initiative = SimpleNamespace(
        id=2,
        organization_id=1,
        name="Family Festival",
        sponsorship_goals="",
        estimated_reach="",
        audience="",
        needs="",
        goals="",
        fundraising_target="",
        deadline=None,
        strategy_meeting_completed_at=None,
    )
    return organization, initiative


def test_strategy_meeting_get_renders_existing_record(monkeypatch):
    organization, initiative = _records()
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

    response = app_module.app.test_client().get("/strategy-meeting")

    assert response.status_code == 200
    assert b"Strategy Meeting" in response.data
    assert b"Estimated Reach" in response.data


def test_invalid_meeting_does_not_commit_or_enqueue(monkeypatch):
    organization, initiative = _records()
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
    enqueue = MagicMock()
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        enqueue,
    )
    commit = MagicMock()
    monkeypatch.setattr(app_module.db.session, "commit", commit)

    response = app_module.app.test_client().post(
        "/strategy-meeting",
        data={"audience": "Families"},
    )

    assert response.status_code == 200
    assert b"Complete the Strategy Meeting fields" in response.data
    assert initiative.strategy_meeting_completed_at is None
    commit.assert_not_called()
    enqueue.assert_not_called()


def test_valid_meeting_saves_and_enqueues_existing_pipeline(monkeypatch):
    organization, initiative = _records()
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
        "get_sponsorship_intelligence",
        lambda *args: None,
    )
    enqueue = MagicMock(
        return_value=(SimpleNamespace(status="pending"), True)
    )
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        enqueue,
    )
    commit = MagicMock()
    monkeypatch.setattr(app_module.db.session, "commit", commit)

    response = app_module.app.test_client().post(
        "/strategy-meeting",
        data={
            "sponsorship_goals": "Fund youth programming",
            "audience": "Families with children ages 6-17",
            "estimated_reach": "500 attendees",
            "needs": "Funding and technology",
            "sponsorship_needs": [
                "Cash Sponsorship",
                "Transportation",
            ],
            "sponsorship_needs_notes": "Transportation for participants",
            "geographic_scope": "Radius",
            "geographic_radius_miles": "25",
            "dream_sponsors": "Local Bank\nRegional Transit",
            "businesses_never_contact": "Excluded Company",
            "campaign_goals": "Secure five aligned partners",
            "fundraising_target": "$25,000",
            "deadline": "2026-10-01",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace")
    assert initiative.sponsorship_goals == "Fund youth programming"
    assert initiative.estimated_reach == "500 attendees"
    assert initiative.sponsorship_needs_json == (
        '["Cash Sponsorship", "Transportation"]'
    )
    assert initiative.geographic_radius_miles == 25
    assert initiative.dream_sponsors_json == (
        '["Local Bank", "Regional Transit"]'
    )
    assert organization.businesses_never_contact_json == (
        '["Excluded Company"]'
    )
    assert initiative.deadline == date(2026, 10, 1)
    assert initiative.strategy_meeting_completed_at is not None
    commit.assert_called_once()
    enqueue.assert_called_once_with(
        organization,
        initiative,
        regenerate=False,
    )


def test_unclear_audience_age_does_not_enqueue_generation(monkeypatch):
    organization, initiative = _records()
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
    enqueue = MagicMock()
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        enqueue,
    )
    commit = MagicMock()
    monkeypatch.setattr(app_module.db.session, "commit", commit)

    response = app_module.app.test_client().post(
        "/strategy-meeting",
        data={
            "sponsorship_goals": "Fund programming",
            "audience": "Community leaders",
            "estimated_reach": "500 attendees",
            "needs": "Funding",
            "campaign_goals": "Secure five partners",
            "fundraising_target": "$25,000",
            "deadline": "2026-10-01",
        },
    )

    assert response.status_code == 200
    assert b"audience age range" in response.data
    assert initiative.strategy_meeting_completed_at is None
    commit.assert_not_called()
    enqueue.assert_not_called()

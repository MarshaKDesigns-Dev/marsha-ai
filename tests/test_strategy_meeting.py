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
        fundraising_target="$25,000",
        deadline="2026-10-01",
        strategy_top_priorities="",
        strategy_priority_sponsors="",
        strategy_success_beyond_fundraising="",
        strategy_concerns_constraints="",
        audience_age_context="unclear",
        sponsor_category_exclusions_json="[]",
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
    assert b"Sponsorship Strategy" in response.data
    assert b"What are your top three priorities for this campaign?" in response.data
    assert b"Are there any sponsors you especially want to pursue first?" in (
        response.data
    )
    assert b"What would make this initiative a success beyond fundraising?" in (
        response.data
    )
    assert b"Are there any concerns or constraints Marsha AI should consider?" in (
        response.data
    )
    for duplicate in (
        b"Audience and Age Range",
        b"Estimated Reach",
        b"Sponsorship Needs",
        b"Campaign Goals",
        b"Fundraising Target",
        b"Deadline",
    ):
        assert duplicate not in response.data


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
        data={"strategy_top_priorities": "Build visibility"},
    )

    assert response.status_code == 200
    assert b"Complete the Sponsorship Strategy fields" in response.data
    assert initiative.strategy_meeting_completed_at is None
    commit.assert_not_called()
    enqueue.assert_not_called()


def test_valid_meeting_saves_enqueues_and_returns_to_dashboard(monkeypatch):
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
    synchronous_generation = MagicMock()
    monkeypatch.setattr(
        app_module,
        "run_workspace_intelligence_generation",
        synchronous_generation,
    )
    commit = MagicMock()
    monkeypatch.setattr(app_module.db.session, "commit", commit)

    response = app_module.app.test_client().post(
        "/strategy-meeting",
        data={
            "strategy_top_priorities": (
                "Build visibility; fund scholarships; create relationships"
            ),
            "strategy_priority_sponsors": "Local Bank and Regional Transit",
            "strategy_success_beyond_fundraising": (
                "Stronger participation and lasting community partnerships"
            ),
            "strategy_concerns_constraints": (
                "Small volunteer team and a fixed event date"
            ),
            "audience_age_context": "mixed_with_minors",
            "category_exclusion_mode": "none",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace")
    assert initiative.strategy_top_priorities == (
        "Build visibility; fund scholarships; create relationships"
    )
    assert initiative.strategy_priority_sponsors == (
        "Local Bank and Regional Transit"
    )
    assert initiative.strategy_success_beyond_fundraising == (
        "Stronger participation and lasting community partnerships"
    )
    assert initiative.strategy_concerns_constraints == (
        "Small volunteer team and a fixed event date"
    )
    assert initiative.audience_age_context == "mixed_with_minors"
    assert initiative.sponsor_category_exclusions_json == "[]"
    assert initiative.audience == ""
    assert initiative.needs == ""
    assert initiative.goals == ""
    assert initiative.fundraising_target == "$25,000"
    assert initiative.deadline == "2026-10-01"
    assert initiative.strategy_meeting_completed_at is not None
    commit.assert_called_once()
    enqueue.assert_called_once_with(
        organization,
        initiative,
    )
    synchronous_generation.assert_not_called()


def test_repeated_meeting_submission_reuses_existing_strategy(monkeypatch):
    organization, initiative = _records()
    intelligence = SimpleNamespace(id=8)
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
        lambda *args: intelligence,
    )
    enqueue = MagicMock()
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        enqueue,
    )
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())

    with app_module.app.test_client() as client:
        response = client.post(
            "/strategy-meeting",
            data={
                "strategy_top_priorities": "Visibility, scholarships, partners",
                "strategy_priority_sponsors": "Local Bank",
                "strategy_success_beyond_fundraising": "Community participation",
                "strategy_concerns_constraints": "Limited volunteer capacity",
                "audience_age_context": "adult_only",
                "category_exclusion_mode": "none",
            },
        )
        with client.session_transaction() as session:
            flashes = session.get("_flashes")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace")
    assert flashes == [
        (
            "success",
            "Strategy inputs updated. Your current strategy has not changed.",
        )
    ]
    enqueue.assert_not_called()


def test_strategy_meeting_get_populates_saved_inputs_and_links_to_strategy(
    monkeypatch,
):
    organization, initiative = _records()
    initiative.strategy_top_priorities = "Visibility, scholarships, partners"
    initiative.strategy_priority_sponsors = "Local Bank"
    initiative.strategy_success_beyond_fundraising = "Community participation"
    initiative.strategy_concerns_constraints = "Limited volunteer capacity"
    intelligence = SimpleNamespace(id=8)
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    monkeypatch.setattr(
        app_module, "get_sponsorship_intelligence", lambda *args: intelligence
    )

    response = app_module.app.test_client().get("/strategy-meeting")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Visibility, scholarships, partners" in html
    assert "Local Bank" in html
    assert "Community participation" in html
    assert "Limited volunteer capacity" in html
    assert "View Strategy" in html
    assert "Save Strategy Inputs" in html
    assert "Build Sponsorship Strategy" not in html


def test_whitespace_only_strategy_answers_do_not_enqueue_generation(monkeypatch):
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
            "strategy_top_priorities": "Build visibility",
            "strategy_priority_sponsors": "None",
            "strategy_success_beyond_fundraising": "Community engagement",
            "strategy_concerns_constraints": "   ",
        },
    )

    assert response.status_code == 200
    assert b"concerns or constraints" in response.data
    assert initiative.strategy_meeting_completed_at is None
    commit.assert_not_called()
    enqueue.assert_not_called()


def test_strategy_meeting_persists_selected_and_custom_exclusions(monkeypatch):
    organization, initiative = _records()
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    monkeypatch.setattr(app_module, "get_sponsorship_intelligence", lambda *args: None)
    monkeypatch.setattr(
        app_module,
        "enqueue_workspace_intelligence_generation",
        MagicMock(return_value=(SimpleNamespace(status="pending"), True)),
    )
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())

    response = app_module.app.test_client().post(
        "/strategy-meeting",
        data={
            "strategy_top_priorities": "Visibility, scholarships, partners",
            "strategy_priority_sponsors": "Local Bank",
            "strategy_success_beyond_fundraising": "Community participation",
            "strategy_concerns_constraints": "Limited volunteer capacity",
            "audience_age_context": "youth",
            "category_exclusion_mode": "selected",
            "sponsor_category_exclusions": ["Alcohol and breweries"],
            "custom_category_exclusions": "Payday lending\nFast fashion",
        },
    )

    assert response.status_code == 302
    assert initiative.audience_age_context == "youth"
    assert app_module.json_list(
        initiative.sponsor_category_exclusions_json
    ) == ["Alcohol and breweries", "Payday lending", "Fast fashion"]

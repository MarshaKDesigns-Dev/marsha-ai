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
    assert b"Complete the Strategy Meeting fields" in response.data
    assert initiative.strategy_meeting_completed_at is None
    commit.assert_not_called()
    enqueue.assert_not_called()


def test_valid_meeting_saves_generates_and_redirects_to_review(monkeypatch):
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
    generate = MagicMock(
        return_value=SimpleNamespace(success=True)
    )
    monkeypatch.setattr(
        app_module,
        "run_inline_workspace_intelligence_generation",
        generate,
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
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace/strategy")
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
    assert initiative.audience == ""
    assert initiative.needs == ""
    assert initiative.goals == ""
    assert initiative.fundraising_target == "$25,000"
    assert initiative.deadline == "2026-10-01"
    assert initiative.strategy_meeting_completed_at is not None
    commit.assert_called_once()
    generate.assert_called_once_with(
        organization,
        initiative,
    )


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
    generate = MagicMock()
    monkeypatch.setattr(
        app_module,
        "run_inline_workspace_intelligence_generation",
        generate,
    )
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())

    response = app_module.app.test_client().post(
        "/strategy-meeting",
        data={
            "strategy_top_priorities": "Visibility, scholarships, partners",
            "strategy_priority_sponsors": "Local Bank",
            "strategy_success_beyond_fundraising": "Community participation",
            "strategy_concerns_constraints": "Limited volunteer capacity",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace/strategy")
    generate.assert_not_called()


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

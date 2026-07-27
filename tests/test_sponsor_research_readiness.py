from types import SimpleNamespace

import pytest

from services.sponsor_research_readiness import (
    audience_age_context_is_clear,
    evaluate_sponsor_research_readiness,
    missing_strategy_meeting_answers,
    strategy_meeting_is_complete,
    validate_approval_status,
)


@pytest.mark.parametrize(
    "audience",
    [
        "Children ages 6-12",
        "Youth ages 13-17",
        "Families and community members of all ages",
        "Adults 21+ only",
    ],
)
def test_existing_rule_recognizes_clear_meeting_age_context(audience):
    assert audience_age_context_is_clear(audience) is True


def test_existing_rule_rejects_unclear_meeting_age_context():
    assert audience_age_context_is_clear("Community leaders") is False


def test_approval_status_accepts_only_three_controlled_values():
    assert validate_approval_status("Pending") == "Pending"
    assert validate_approval_status("Approved") == "Approved"
    assert validate_approval_status("Rejected") == "Rejected"

    with pytest.raises(ValueError):
        validate_approval_status("approved")
    with pytest.raises(ValueError):
        validate_approval_status("Anything Else")


def test_meeting_and_approved_asset_are_required():
    initiative = SimpleNamespace(
        strategy_meeting_completed_at=None,
        strategy_top_priorities="Visibility, funding, relationships",
        strategy_priority_sponsors="Regional Bank",
        strategy_success_beyond_fundraising="Community engagement",
        strategy_concerns_constraints="Limited staff capacity",
    )
    approved = SimpleNamespace(
        approval_status="Approved",
        is_active=True,
    )

    missing_meeting = evaluate_sponsor_research_readiness(
        initiative,
        [approved],
    )
    assert missing_meeting.reason_code == "strategy_meeting_required"

    initiative.strategy_meeting_completed_at = object()
    missing_approval = evaluate_sponsor_research_readiness(
        initiative,
        [SimpleNamespace(approval_status="Pending", is_active=True)],
    )
    assert missing_approval.reason_code == (
        "approved_sponsorship_asset_required"
    )

    ready = evaluate_sponsor_research_readiness(
        initiative,
        [approved],
    )
    assert ready.allowed is True


def test_meeting_completion_requires_only_four_focused_answers():
    initiative = SimpleNamespace(
        strategy_meeting_completed_at=object(),
        strategy_top_priorities="Visibility, funding, relationships",
        strategy_priority_sponsors="Regional Bank",
        strategy_success_beyond_fundraising="Community engagement",
        strategy_concerns_constraints="Limited staff capacity",
        sponsorship_goals="",
        audience="",
        estimated_reach="",
        needs="",
        goals="",
        fundraising_target="",
        deadline=None,
    )

    assert missing_strategy_meeting_answers(initiative) == []
    assert strategy_meeting_is_complete(initiative) is True


def test_missing_focused_answer_keeps_meeting_incomplete():
    initiative = SimpleNamespace(
        strategy_meeting_completed_at=object(),
        strategy_top_priorities="Visibility",
        strategy_priority_sponsors="Regional Bank",
        strategy_success_beyond_fundraising="Community engagement",
        strategy_concerns_constraints=" ",
    )

    assert missing_strategy_meeting_answers(initiative) == [
        "concerns or constraints"
    ]
    assert strategy_meeting_is_complete(initiative) is False


def test_legacy_intelligence_satisfies_meeting_completion_only():
    initiative = SimpleNamespace(strategy_meeting_completed_at=None)

    assert strategy_meeting_is_complete(
        initiative,
        intelligence=SimpleNamespace(id=1),
    )
    decision = evaluate_sponsor_research_readiness(
        initiative,
        [],
        intelligence=SimpleNamespace(id=1),
    )
    assert decision.allowed is False
    assert decision.reason_code == "approved_sponsorship_asset_required"

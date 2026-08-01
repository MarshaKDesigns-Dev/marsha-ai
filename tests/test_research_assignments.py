from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app import ResearchAssignment
from services import research_assignments as assignments


NOW = datetime(2026, 7, 31, 12, 0)


def records():
    return (
        SimpleNamespace(id=1),
        SimpleNamespace(id=2, organization_id=1),
        SimpleNamespace(id=3),
    )


def query_returning(*values):
    query = MagicMock()
    query.filter_by.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.with_for_update.return_value = query
    query.first.side_effect = values
    return query


def test_model_has_durable_claim_fields_and_indexes():
    columns = ResearchAssignment.__table__.c
    assert columns.active_key.unique is True
    for name in (
        "worker_id", "lease_expires_at", "available_at", "attempt_count"
    ):
        assert name in columns
    assert "ix_research_assignment_claim" in {
        index.name for index in ResearchAssignment.__table__.indexes
    }


def test_enqueue_creates_ready_assignment_and_reuses_active_assignment():
    organization, initiative, asset = records()
    session = MagicMock()
    session.query.return_value = query_returning(None)
    queued, created = assignments.enqueue_assignment(
        organization, initiative, asset, session=session, now=NOW
    )
    assert created is True
    assert queued.status == "ready"
    assert queued.active_key == "1:2:3"
    assert queued.worker_id is None
    existing_session = MagicMock()
    existing_session.query.return_value = query_returning(queued)
    reused, created = assignments.enqueue_assignment(
        organization, initiative, asset, session=existing_session
    )
    assert reused is queued
    assert created is False


def test_enqueue_uniqueness_race_reuses_database_winner():
    organization, initiative, asset = records()
    winner = ResearchAssignment(id=9, active_key="1:2:3", status="ready")
    session = MagicMock()
    session.query.return_value = query_returning(None, winner)
    session.commit.side_effect = IntegrityError("insert", {}, Exception())
    queued, created = assignments.enqueue_assignment(
        organization, initiative, asset, session=session, now=NOW
    )
    assert queued is winner
    assert created is False
    session.rollback.assert_called_once()


def test_claim_sets_worker_attempt_and_lease_and_terminal_clears_claim():
    queued = ResearchAssignment(
        id=1, status="ready", active_key="1:2:3",
        available_at=NOW, attempt_count=0,
    )
    session = MagicMock()
    session.query.return_value = query_returning(queued)
    session.get_bind.return_value.dialect.name = "sqlite"
    claimed = assignments.claim_next_assignment(
        "worker-1", session=session, now=NOW, lease_seconds=300
    )
    assert claimed.status == "working"
    assert claimed.worker_id == "worker-1"
    assert claimed.attempt_count == 1
    assert claimed.lease_expires_at == NOW + timedelta(seconds=300)
    result = SimpleNamespace(model_dump=lambda **kwargs: {"name": "Sponsor"})
    assignments.mark_completed(claimed, [result], session=session, now=NOW)
    assert claimed.status == "completed"
    assert claimed.active_key is None
    assert claimed.lease_expires_at is None


def test_expired_assignment_can_be_reclaimed_and_active_one_is_not_selected():
    stale = ResearchAssignment(
        id=2, status="working", active_key="1:2:3", attempt_count=1,
        available_at=NOW, lease_expires_at=NOW - timedelta(seconds=1),
    )
    session = MagicMock()
    session.query.return_value = query_returning(stale)
    session.get_bind.return_value.dialect.name = "sqlite"
    assert assignments.claim_next_assignment(
        "worker-2", session=session, now=NOW
    ) is stale
    assert stale.worker_id == "worker-2"
    assert stale.attempt_count == 2
    empty_session = MagicMock()
    empty_session.query.return_value = query_returning(None)
    empty_session.get_bind.return_value.dialect.name = "sqlite"
    assert assignments.claim_next_assignment(
        "worker-3", session=empty_session, now=NOW
    ) is None


def test_failure_is_terminal_and_allows_future_active_key():
    assignment = ResearchAssignment(
        status="working", active_key="1:2:3", lease_expires_at=NOW
    )
    session = MagicMock()
    assignments.mark_needs_attention(
        assignment, "Safe failure.", session=session, now=NOW
    )
    assert assignment.status == "needs_attention"
    assert assignment.error_details == "Safe failure."
    assert assignment.active_key is None
    assert assignment.results_json == "[]"

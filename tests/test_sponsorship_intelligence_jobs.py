from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app import SponsorshipIntelligenceJob
from services import sponsorship_intelligence_jobs as jobs


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _organization_and_initiative():
    return (
        SimpleNamespace(id=1),
        SimpleNamespace(id=10, organization_id=1),
    )


def _query_returning(*values):
    query = MagicMock()
    query.filter_by.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.with_for_update.return_value = query
    query.first.side_effect = values
    return query


def test_job_model_has_unique_active_key_and_required_indexes():
    assert SponsorshipIntelligenceJob.__table__.c.active_key.unique is True
    constraint_names = {
        constraint.name
        for constraint in SponsorshipIntelligenceJob.__table__.constraints
    }
    assert "ck_intelligence_job_status" in constraint_names
    index_names = {
        index.name for index in SponsorshipIntelligenceJob.__table__.indexes
    }
    assert "ix_intelligence_job_pending_lookup" in index_names
    assert "ix_intelligence_job_initiative_history" in index_names
    assert "ix_intelligence_job_lease_recovery" in index_names


def test_enqueue_creates_pending_job_and_stores_regenerate():
    organization, initiative = _organization_and_initiative()
    session = MagicMock()
    session.query.return_value = _query_returning(None)

    job, created = jobs.enqueue_job(
        organization,
        initiative,
        regenerate=True,
        session=session,
        now=NOW,
    )

    assert created is True
    assert job.status == jobs.STATUS_PENDING
    assert job.regenerate is True
    assert job.active_key == "1:10"
    session.add.assert_called_once_with(job)
    session.commit.assert_called_once()


def test_enqueue_returns_existing_active_job():
    organization, initiative = _organization_and_initiative()
    existing = SponsorshipIntelligenceJob(id=7, active_key="1:10")
    session = MagicMock()
    session.query.return_value = _query_returning(existing)

    job, created = jobs.enqueue_job(
        organization,
        initiative,
        session=session,
    )

    assert job is existing
    assert created is False
    session.add.assert_not_called()


def test_enqueue_uniqueness_race_returns_winning_job():
    organization, initiative = _organization_and_initiative()
    winner = SponsorshipIntelligenceJob(id=8, active_key="1:10")
    session = MagicMock()
    session.query.return_value = _query_returning(None, winner)
    session.commit.side_effect = IntegrityError("insert", {}, Exception())

    job, created = jobs.enqueue_job(
        organization,
        initiative,
        session=session,
        now=NOW,
    )

    assert job is winner
    assert created is False
    session.rollback.assert_called_once()


def test_terminal_status_clears_active_key_and_preserves_job():
    session = MagicMock()
    completed = SponsorshipIntelligenceJob(active_key="1:10")
    failed = SponsorshipIntelligenceJob(active_key="1:10")

    jobs.mark_completed(completed, session=session, now=NOW)
    jobs.mark_failed(
        failed,
        message="Safe failure.",
        error_code="generation_failed",
        session=session,
        now=NOW,
    )

    assert completed.status == jobs.STATUS_COMPLETED
    assert completed.active_key is None
    assert failed.status == jobs.STATUS_FAILED
    assert failed.active_key is None
    assert failed.message == "Safe failure."
    assert session.delete.call_count == 0


def test_claim_commits_processing_state_before_return(monkeypatch):
    job = SponsorshipIntelligenceJob(
        id=1,
        status=jobs.STATUS_PENDING,
        attempt_count=0,
        active_key="1:10",
        available_at=NOW,
    )
    session = MagicMock()
    session.query.return_value = _query_returning(job)
    session.get_bind.return_value.dialect.name = "postgresql"

    claimed = jobs.claim_next_job(
        "worker-1",
        session=session,
        now=NOW,
    )

    assert claimed is job
    assert job.status == jobs.STATUS_PROCESSING
    assert job.worker_id == "worker-1"
    assert job.attempt_count == 1
    assert job.lease_expires_at == NOW + timedelta(seconds=600)
    session.commit.assert_called_once()


def test_claim_does_not_reclaim_when_no_eligible_job():
    session = MagicMock()
    session.query.return_value = _query_returning(None)
    session.get_bind.return_value.dialect.name = "sqlite"

    assert jobs.claim_next_job("worker-1", session=session, now=NOW) is None
    session.commit.assert_not_called()


def test_expired_job_is_reclaimed():
    stale = SponsorshipIntelligenceJob(
        id=2,
        status=jobs.STATUS_PROCESSING,
        attempt_count=1,
        active_key="1:10",
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    session = MagicMock()
    session.query.return_value = _query_returning(stale)
    session.get_bind.return_value.dialect.name = "sqlite"

    claimed = jobs.claim_next_job("worker-2", session=session, now=NOW)

    assert claimed is stale
    assert stale.worker_id == "worker-2"
    assert stale.attempt_count == 2


def test_maximum_attempts_marks_stale_job_failed_safely():
    stale = SponsorshipIntelligenceJob(
        id=3,
        status=jobs.STATUS_PROCESSING,
        attempt_count=3,
        active_key="1:10",
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    session = MagicMock()
    session.query.return_value = _query_returning(stale, None)
    session.get_bind.return_value.dialect.name = "sqlite"

    claimed = jobs.claim_next_job(
        "worker-2",
        session=session,
        now=NOW,
        max_attempts=3,
    )

    assert claimed is None
    assert stale.status == jobs.STATUS_FAILED
    assert stale.active_key is None
    assert stale.message == jobs.MAX_ATTEMPTS_MESSAGE

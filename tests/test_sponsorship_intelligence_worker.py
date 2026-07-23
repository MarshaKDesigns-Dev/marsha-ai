from datetime import UTC, datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import SponsorshipIntelligenceJob, app, db
from services.sponsorship_intelligence_jobs import claim_next_job
from services.sponsorship_intelligence_worker import (
    UNEXPECTED_FAILURE_MESSAGE,
    configure_worker_logging,
    inspect_eligible_jobs,
    process_next_job,
    run_worker,
)


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _job():
    return SimpleNamespace(
        id=1,
        organization_id=10,
        initiative_id=20,
        regenerate=True,
        attempt_count=1,
        status="processing",
    )


@pytest.fixture
def job_session():
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_startup_database_and_polling_logs_are_visible():
    stream = StringIO()

    run_worker(
        worker_id="worker-1",
        workflow_budget_seconds=240.0,
        lease_seconds=600.0,
        poll_interval_seconds=3.0,
        max_attempts=3,
        process=MagicMock(return_value=False),
        sleeper=MagicMock(),
        clock=lambda: 0.0,
        log_stream=stream,
        max_iterations=1,
    )

    output = stream.getvalue()
    assert (
        "sponsorship_intelligence_worker_started worker_id=worker-1 "
        "database_dialect=sqlite workflow_budget_seconds=240.0 "
        "lease_seconds=600.0 poll_interval_seconds=3.0 max_attempts=3"
    ) in output
    assert (
        "sponsorship_intelligence_worker_polling_loop_entered "
        "worker_id=worker-1"
    ) in output


def test_idle_logging_is_throttled_to_once_per_60_seconds():
    stream = StringIO()
    times = iter([0.0, 30.0, 60.0])

    run_worker(
        worker_id="worker-1",
        workflow_budget_seconds=240.0,
        lease_seconds=600.0,
        poll_interval_seconds=3.0,
        max_attempts=3,
        process=MagicMock(return_value=False),
        sleeper=MagicMock(),
        clock=lambda: next(times),
        log_stream=stream,
        max_iterations=3,
    )

    assert stream.getvalue().count(
        "sponsorship_intelligence_worker_idle"
    ) == 2


def test_eligible_job_diagnostic_returns_only_safe_queue_fields(job_session):
    job_session.add(
        SponsorshipIntelligenceJob(
            organization_id=1,
            initiative_id=10,
            status="pending",
            regenerate=False,
            attempt_count=0,
            active_key="1:10",
            available_at=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    job_session.commit()

    diagnostic = inspect_eligible_jobs(session=job_session)

    assert diagnostic["eligible_pending_count"] == 1
    assert diagnostic["oldest_eligible_job_id"] is not None
    assert diagnostic["database_utc_time"] is not None
    assert diagnostic["oldest_status"] == "pending"
    assert diagnostic["oldest_attempt_count"] == 0
    assert set(diagnostic) == {
        "eligible_pending_count",
        "oldest_eligible_job_id",
        "database_utc_time",
        "oldest_available_at",
        "oldest_status",
        "oldest_attempt_count",
    }


def test_valid_pending_job_is_claimed(job_session):
    job = SponsorshipIntelligenceJob(
        organization_id=1,
        initiative_id=10,
        status="pending",
        regenerate=False,
        attempt_count=0,
        active_key="1:10",
        available_at=NOW - timedelta(seconds=1),
    )
    job_session.add(job)
    job_session.commit()

    claimed = claim_next_job(
        "worker-1",
        session=job_session,
        now=NOW,
    )

    assert claimed.id == job.id
    assert claimed.status == "processing"
    assert claimed.attempt_count == 1


def test_future_pending_job_is_not_claimed(job_session):
    job_session.add(
        SponsorshipIntelligenceJob(
            organization_id=1,
            initiative_id=10,
            status="pending",
            regenerate=False,
            attempt_count=0,
            active_key="1:10",
            available_at=NOW + timedelta(seconds=1),
        )
    )
    job_session.commit()

    assert claim_next_job(
        "worker-1",
        session=job_session,
        now=NOW,
    ) is None


def test_expired_processing_lease_is_reclaimable(job_session):
    job = SponsorshipIntelligenceJob(
        organization_id=1,
        initiative_id=10,
        status="processing",
        regenerate=False,
        attempt_count=1,
        active_key="1:10",
        available_at=NOW - timedelta(seconds=10),
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    job_session.add(job)
    job_session.commit()

    claimed = claim_next_job(
        "worker-2",
        session=job_session,
        now=NOW,
    )

    assert claimed.id == job.id
    assert claimed.worker_id == "worker-2"
    assert claimed.attempt_count == 2


def test_worker_passes_background_budget_and_completes_atomically(monkeypatch):
    stream = StringIO()
    configure_worker_logging(stream)
    job = _job()
    persisted = MagicMock()
    generated = MagicMock(
        return_value=SimpleNamespace(
            success=True,
            status="generated",
            message="Saved.",
            generation_step=None,
        )
    )
    completed = MagicMock()
    monkeypatch.setattr(
        "services.sponsorship_intelligence_worker.mark_completed",
        completed,
    )
    database_session = MagicMock()
    monkeypatch.setattr(
        "services.sponsorship_intelligence_worker.db.session",
        database_session,
    )

    assert process_next_job(
        worker_id="worker",
        workflow_budget_seconds=240.0,
        lease_seconds=600.0,
        max_attempts=3,
        claim=MagicMock(return_value=job),
        generate=generated,
        persist=persisted,
    ) is True

    assert generated.call_args.kwargs["workflow_budget_seconds"] == 240.0
    deferred_persist = generated.call_args.kwargs["persist"]
    deferred_persist("org", "initiative", "result")
    persisted.assert_called_once_with(
        "org",
        "initiative",
        "result",
        session=database_session,
        commit=False,
    )
    completed.assert_called_once_with(
        job,
        session=database_session,
        commit=False,
    )
    database_session.commit.assert_called_once()
    output = stream.getvalue()
    assert "sponsorship_intelligence_job_claimed" in output
    assert "job_id=1 organization_id=10 initiative_id=20" in output
    assert "attempt_count=1 status=processing" in output
    assert "sponsorship_intelligence_generation_started" in output
    assert "sponsorship_intelligence_job_completed" in output


def test_worker_emits_persistence_and_completion_lifecycle_logs_in_order(
    monkeypatch,
):
    stream = StringIO()
    configure_worker_logging(stream)
    job = _job()
    completed = MagicMock()
    monkeypatch.setattr(
        "services.sponsorship_intelligence_worker.mark_completed",
        completed,
    )

    def generate(*args, lifecycle_logger, persist, **kwargs):
        lifecycle_logger("organization_analysis_started")
        lifecycle_logger("before_openai_request")
        lifecycle_logger("after_openai_request")
        lifecycle_logger("organization_analysis_completed")
        persist(MagicMock(), MagicMock(), MagicMock())
        return SimpleNamespace(success=True)

    with app.app_context():
        process_next_job(
            worker_id="worker",
            workflow_budget_seconds=240.0,
            lease_seconds=600.0,
            max_attempts=3,
            claim=MagicMock(return_value=job),
            generate=generate,
            persist=MagicMock(return_value=MagicMock()),
        )

    output = stream.getvalue()
    expected = [
        "organization_analysis_started",
        "before_openai_request",
        "after_openai_request",
        "organization_analysis_completed",
        "persist_sponsorship_intelligence_started",
        "persist_sponsorship_intelligence_completed",
        "mark_completed_started",
        "mark_completed_completed",
    ]
    positions = [output.index(event) for event in expected]
    assert positions == sorted(positions)
    for event in expected:
        line = next(
            line for line in output.splitlines() if line.startswith(event)
        )
        assert "worker_id=worker" in line
        assert f"job_id={job.id}" in line
        assert f"organization_id={job.organization_id}" in line
        assert f"initiative_id={job.initiative_id}" in line


def test_worker_timeout_marks_failed_with_safe_message(monkeypatch):
    stream = StringIO()
    configure_worker_logging(stream)
    job = _job()
    failed = MagicMock()
    monkeypatch.setattr(
        "services.sponsorship_intelligence_worker.mark_failed",
        failed,
    )
    result = SimpleNamespace(
        success=False,
        status="generation_timeout",
        message=(
            "Sponsorship intelligence generation took too long. "
            "Please try again."
        ),
        generation_step="sponsorship_assets",
    )

    with app.app_context():
        process_next_job(
            worker_id="worker",
            workflow_budget_seconds=240.0,
            lease_seconds=600.0,
            max_attempts=3,
            claim=MagicMock(return_value=job),
            generate=MagicMock(return_value=result),
        )

    assert failed.call_args.kwargs["message"] == result.message
    assert failed.call_args.kwargs["generation_step"] == "sponsorship_assets"
    output = stream.getvalue()
    assert "error_code=generation_timeout" in output
    assert "generation_step=sponsorship_assets" in output
    assert result.message not in output


def test_worker_unexpected_failure_stores_no_raw_detail(monkeypatch):
    stream = StringIO()
    configure_worker_logging(stream)
    job = _job()
    failed = MagicMock()
    monkeypatch.setattr(
        "services.sponsorship_intelligence_worker.mark_failed",
        failed,
    )

    with app.app_context():
        process_next_job(
            worker_id="worker",
            workflow_budget_seconds=240.0,
            lease_seconds=600.0,
            max_attempts=3,
            claim=MagicMock(return_value=job),
            generate=MagicMock(
                side_effect=RuntimeError("secret provider detail")
            ),
        )

    message = failed.call_args.kwargs["message"]
    assert message == UNEXPECTED_FAILURE_MESSAGE
    assert "secret provider detail" not in message
    output = stream.getvalue()
    assert "error_code=unexpected_worker_error" in output
    assert "secret provider detail" not in output
    for forbidden in (
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "prompt content",
        "response body",
        "user-entered content",
    ):
        assert forbidden not in output


def test_worker_loop_continues_after_unexpected_iteration_error():
    stream = StringIO()
    process = MagicMock(side_effect=[RuntimeError("boom"), False])
    sleeper = MagicMock()

    run_worker(
        worker_id="worker",
        workflow_budget_seconds=240.0,
        lease_seconds=600.0,
        poll_interval_seconds=3.0,
        max_attempts=3,
        process=process,
        sleeper=sleeper,
        clock=iter([0.0, 61.0]).__next__,
        log_stream=stream,
        max_iterations=2,
    )

    assert process.call_count == 2
    assert sleeper.call_count == 2
    output = stream.getvalue()
    assert "error_code=unexpected_loop_error" in output
    assert "boom" not in output

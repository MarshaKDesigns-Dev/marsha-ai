from types import SimpleNamespace
from unittest.mock import MagicMock

from app import app
from services.sponsorship_intelligence_worker import (
    UNEXPECTED_FAILURE_MESSAGE,
    process_next_job,
    run_worker,
)


def _job():
    return SimpleNamespace(
        id=1,
        organization_id=10,
        initiative_id=20,
        regenerate=True,
    )


def test_worker_passes_background_budget_and_completes_atomically(monkeypatch):
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


def test_worker_timeout_marks_failed_with_safe_message(monkeypatch):
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


def test_worker_unexpected_failure_stores_no_raw_detail(monkeypatch):
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


def test_worker_loop_continues_after_unexpected_iteration_error():
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
        max_iterations=2,
    )

    assert process.call_count == 2
    assert sleeper.call_count == 2

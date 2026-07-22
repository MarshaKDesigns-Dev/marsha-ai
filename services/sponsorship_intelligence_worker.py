"""Long-running worker for durable sponsorship intelligence jobs."""

from __future__ import annotations

import logging
import os
import socket
from time import sleep
from typing import Callable

from app import app, db
from services.generate_sponsorship_intelligence import (
    generate_workspace_intelligence,
)
from services.sponsorship_intelligence_jobs import (
    claim_next_job,
    mark_completed,
    mark_failed,
)
from services.sponsorship_intelligence_persistence import (
    persist_sponsorship_intelligence,
)


DEFAULT_BACKGROUND_WORKFLOW_BUDGET_SECONDS = 240.0
DEFAULT_JOB_LEASE_SECONDS = 600.0
DEFAULT_JOB_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_JOB_MAX_ATTEMPTS = 3
UNEXPECTED_FAILURE_MESSAGE = (
    "Sponsorship intelligence could not be generated. Please try again."
)

logger = logging.getLogger(__name__)


def _float_setting(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_setting(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def build_worker_id() -> str:
    """Return a stable identity for this Railway worker process."""

    service = os.getenv("RAILWAY_SERVICE_ID", "local")
    replica = os.getenv("RAILWAY_REPLICA_ID", socket.gethostname())
    deployment = os.getenv("RAILWAY_DEPLOYMENT_ID", "development")
    return f"{service}:{replica}:{deployment}:{os.getpid()}"


def process_next_job(
    *,
    worker_id: str,
    workflow_budget_seconds: float,
    lease_seconds: float,
    max_attempts: int,
    claim=claim_next_job,
    generate=generate_workspace_intelligence,
    persist=persist_sponsorship_intelligence,
) -> bool:
    """Claim and process one job, returning whether work was found."""

    job = claim(
        worker_id,
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
    )
    if job is None:
        return False

    def persist_without_commit(organization, initiative, result):
        return persist(
            organization,
            initiative,
            result,
            session=db.session,
            commit=False,
        )

    try:
        result = generate(
            job.organization_id,
            job.initiative_id,
            regenerate=job.regenerate,
            workflow_budget_seconds=workflow_budget_seconds,
            persist=persist_without_commit,
        )

        if result.success:
            mark_completed(
                job,
                session=db.session,
                commit=False,
            )
            db.session.commit()
            return True

        db.session.rollback()
        mark_failed(
            job,
            message=result.message,
            error_code=result.status,
            generation_step=result.generation_step,
            session=db.session,
        )
        return True

    except Exception:
        db.session.rollback()
        logger.error(
            (
                "sponsorship_intelligence_job_failed "
                "job_id=%s organization_id=%s initiative_id=%s"
            ),
            getattr(job, "id", None),
            getattr(job, "organization_id", None),
            getattr(job, "initiative_id", None),
        )
        mark_failed(
            job,
            message=UNEXPECTED_FAILURE_MESSAGE,
            error_code="unexpected_worker_error",
            session=db.session,
        )
        return True


def run_worker(
    *,
    worker_id: str | None = None,
    workflow_budget_seconds: float | None = None,
    lease_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
    max_attempts: int | None = None,
    process: Callable[..., bool] = process_next_job,
    sleeper: Callable[[float], None] = sleep,
    max_iterations: int | None = None,
) -> None:
    """Continuously process jobs without allowing one failure to exit."""

    resolved_worker_id = worker_id or build_worker_id()
    resolved_budget = workflow_budget_seconds or _float_setting(
        "BACKGROUND_WORKFLOW_BUDGET_SECONDS",
        DEFAULT_BACKGROUND_WORKFLOW_BUDGET_SECONDS,
    )
    resolved_lease = lease_seconds or _float_setting(
        "GENERATION_JOB_LEASE_SECONDS",
        DEFAULT_JOB_LEASE_SECONDS,
    )
    resolved_poll = poll_interval_seconds or _float_setting(
        "GENERATION_JOB_POLL_INTERVAL_SECONDS",
        DEFAULT_JOB_POLL_INTERVAL_SECONDS,
    )
    resolved_attempts = max_attempts or _int_setting(
        "GENERATION_JOB_MAX_ATTEMPTS",
        DEFAULT_JOB_MAX_ATTEMPTS,
    )

    iterations = 0
    with app.app_context():
        while max_iterations is None or iterations < max_iterations:
            iterations += 1
            try:
                found_job = process(
                    worker_id=resolved_worker_id,
                    workflow_budget_seconds=resolved_budget,
                    lease_seconds=resolved_lease,
                    max_attempts=resolved_attempts,
                )
            except Exception:
                db.session.rollback()
                logger.error("sponsorship_intelligence_worker_iteration_failed")
                found_job = False

            if not found_job:
                sleeper(resolved_poll)


if __name__ == "__main__":
    run_worker()

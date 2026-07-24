"""Long-running worker for durable sponsorship intelligence jobs."""

from __future__ import annotations

import logging
import os
import socket
import sys
from time import monotonic, sleep
from typing import Callable, TextIO

from sqlalchemy import func, select

from app import SponsorshipIntelligenceJob
from application import app
from extensions import db
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


def configure_worker_logging(stream: TextIO | None = None) -> None:
    """Send controlled worker lifecycle logs to Railway-visible stdout."""

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def inspect_eligible_jobs(*, session=None) -> dict:
    """Return safe queue diagnostics without connection or user data."""

    database_session = session or db.session
    database_now = database_session.scalar(select(func.now()))
    eligible = database_session.query(SponsorshipIntelligenceJob).filter(
        SponsorshipIntelligenceJob.status == "pending",
        SponsorshipIntelligenceJob.available_at <= database_now,
    )
    oldest = eligible.order_by(
        SponsorshipIntelligenceJob.available_at.asc(),
        SponsorshipIntelligenceJob.id.asc(),
    ).first()
    return {
        "eligible_pending_count": eligible.count(),
        "oldest_eligible_job_id": getattr(oldest, "id", None),
        "database_utc_time": database_now,
        "oldest_available_at": getattr(oldest, "available_at", None),
        "oldest_status": getattr(oldest, "status", None),
        "oldest_attempt_count": getattr(oldest, "attempt_count", None),
    }


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

    logger.info(
        (
            "sponsorship_intelligence_job_claimed worker_id=%s job_id=%s "
            "organization_id=%s initiative_id=%s attempt_count=%s "
            "status=%s"
        ),
        worker_id,
        getattr(job, "id", None),
        getattr(job, "organization_id", None),
        getattr(job, "initiative_id", None),
        getattr(job, "attempt_count", None),
        getattr(job, "status", None),
    )
    logger.info(
        (
            "sponsorship_intelligence_generation_started worker_id=%s "
            "job_id=%s organization_id=%s initiative_id=%s status=processing"
        ),
        worker_id,
        getattr(job, "id", None),
        getattr(job, "organization_id", None),
        getattr(job, "initiative_id", None),
    )

    def log_lifecycle(event: str) -> None:
        logger.info(
            (
                "%s worker_id=%s job_id=%s organization_id=%s "
                "initiative_id=%s"
            ),
            event,
            worker_id,
            getattr(job, "id", None),
            getattr(job, "organization_id", None),
            getattr(job, "initiative_id", None),
        )

    def persist_without_commit(organization, initiative, result):
        log_lifecycle("persist_sponsorship_intelligence_started")
        record = persist(
            organization,
            initiative,
            result,
            session=db.session,
            commit=False,
        )
        log_lifecycle("persist_sponsorship_intelligence_completed")
        return record

    try:
        result = generate(
            job.organization_id,
            job.initiative_id,
            regenerate=job.regenerate,
            workflow_budget_seconds=workflow_budget_seconds,
            persist=persist_without_commit,
            lifecycle_logger=log_lifecycle,
        )

        if result.success:
            log_lifecycle("mark_completed_started")
            mark_completed(
                job,
                session=db.session,
                commit=False,
            )
            log_lifecycle("mark_completed_completed")
            db.session.commit()
            logger.info(
                (
                    "sponsorship_intelligence_job_completed worker_id=%s "
                    "job_id=%s organization_id=%s initiative_id=%s "
                    "status=completed"
                ),
                worker_id,
                getattr(job, "id", None),
                getattr(job, "organization_id", None),
                getattr(job, "initiative_id", None),
            )
            return True

        db.session.rollback()
        mark_failed(
            job,
            message=result.message,
            error_code=result.status,
            generation_step=result.generation_step,
            session=db.session,
        )
        logger.warning(
            (
                "sponsorship_intelligence_job_failed worker_id=%s job_id=%s "
                "organization_id=%s initiative_id=%s status=failed "
                "generation_step=%s error_code=%s"
            ),
            worker_id,
            getattr(job, "id", None),
            getattr(job, "organization_id", None),
            getattr(job, "initiative_id", None),
            getattr(result, "generation_step", None),
            getattr(result, "status", None),
        )
        return True

    except Exception:
        db.session.rollback()
        logger.error(
            (
                "sponsorship_intelligence_job_failed "
                "worker_id=%s job_id=%s organization_id=%s initiative_id=%s "
                "status=failed generation_step=None "
                "error_code=unexpected_worker_error"
            ),
            worker_id,
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
    clock: Callable[[], float] = monotonic,
    log_stream: TextIO | None = None,
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

    configure_worker_logging(log_stream)
    iterations = 0
    last_idle_log_at = None
    with app.app_context():
        database_dialect = db.session.get_bind().dialect.name
        logger.info(
            (
                "sponsorship_intelligence_worker_started worker_id=%s "
                "database_dialect=%s workflow_budget_seconds=%s "
                "lease_seconds=%s poll_interval_seconds=%s max_attempts=%s"
            ),
            resolved_worker_id,
            database_dialect,
            resolved_budget,
            resolved_lease,
            resolved_poll,
            resolved_attempts,
        )
        logger.info(
            "sponsorship_intelligence_worker_polling_loop_entered worker_id=%s",
            resolved_worker_id,
        )
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
                logger.error(
                    (
                        "sponsorship_intelligence_worker_iteration_failed "
                        "worker_id=%s status=failed "
                        "generation_step=None error_code=unexpected_loop_error"
                    ),
                    resolved_worker_id,
                )
                found_job = False

            if not found_job:
                current_time = clock()
                if (
                    last_idle_log_at is None
                    or current_time - last_idle_log_at >= 60.0
                ):
                    logger.info(
                        (
                            "sponsorship_intelligence_worker_idle worker_id=%s "
                            "status=idle"
                        ),
                        resolved_worker_id,
                    )
                    last_idle_log_at = current_time
                sleeper(resolved_poll)


if __name__ == "__main__":
    run_worker()

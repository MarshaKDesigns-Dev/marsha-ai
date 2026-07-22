"""PostgreSQL-backed queue operations for sponsorship intelligence jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, or_
from sqlalchemy.exc import IntegrityError


STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_PROCESSING)

MAX_ATTEMPTS_MESSAGE = (
    "Sponsorship intelligence generation could not be completed after "
    "multiple attempts. Please try again."
)


def _models():
    from app import SponsorshipIntelligenceJob, db

    return SponsorshipIntelligenceJob, db


def _session(session=None):
    _, db = _models()
    return session or db.session


def active_job_key(organization_id: int, initiative_id: int) -> str:
    return f"{organization_id}:{initiative_id}"


def get_active_job(
    organization_id: int,
    initiative_id: int,
    *,
    session=None,
):
    Job, _ = _models()
    return (
        _session(session)
        .query(Job)
        .filter_by(
            active_key=active_job_key(organization_id, initiative_id)
        )
        .first()
    )


def get_latest_job(
    organization_id: int,
    initiative_id: int,
    *,
    session=None,
):
    Job, _ = _models()
    return (
        _session(session)
        .query(Job)
        .filter_by(
            organization_id=organization_id,
            initiative_id=initiative_id,
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .first()
    )


def enqueue_job(
    organization: Any,
    initiative: Any,
    *,
    regenerate: bool = False,
    session=None,
    now: datetime | None = None,
):
    """Create one pending job or return the existing active job."""

    organization_id = getattr(organization, "id", None)
    initiative_id = getattr(initiative, "id", None)
    if not organization_id or not initiative_id:
        raise ValueError("Persisted organization and initiative are required.")
    if getattr(initiative, "organization_id", None) != organization_id:
        raise ValueError("The initiative does not belong to the organization.")

    Job, _ = _models()
    database_session = _session(session)
    key = active_job_key(organization_id, initiative_id)
    existing = get_active_job(
        organization_id,
        initiative_id,
        session=database_session,
    )
    if existing is not None:
        return existing, False

    timestamp = now or datetime.now(UTC)
    job = Job(
        organization_id=organization_id,
        initiative_id=initiative_id,
        status=STATUS_PENDING,
        regenerate=bool(regenerate),
        active_key=key,
        available_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    database_session.add(job)

    try:
        database_session.commit()
        return job, True
    except IntegrityError:
        database_session.rollback()
        existing = get_active_job(
            organization_id,
            initiative_id,
            session=database_session,
        )
        if existing is None:
            raise
        return existing, False


def mark_processing(
    job,
    *,
    worker_id: str,
    lease_seconds: float,
    now: datetime,
) -> None:
    job.status = STATUS_PROCESSING
    job.worker_id = worker_id
    job.started_at = job.started_at or now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempt_count = (job.attempt_count or 0) + 1
    job.updated_at = now


def mark_completed(
    job,
    *,
    generation_step: str | None = None,
    session=None,
    commit: bool = True,
    now: datetime | None = None,
) -> None:
    database_session = _session(session)
    timestamp = now or datetime.now(UTC)
    job.status = STATUS_COMPLETED
    job.generation_step = generation_step
    job.error_code = None
    job.message = None
    job.active_key = None
    job.lease_expires_at = None
    job.completed_at = timestamp
    job.updated_at = timestamp
    if commit:
        database_session.commit()
    else:
        database_session.flush()


def mark_failed(
    job,
    *,
    message: str,
    error_code: str,
    generation_step: str | None = None,
    session=None,
    commit: bool = True,
    now: datetime | None = None,
) -> None:
    database_session = _session(session)
    timestamp = now or datetime.now(UTC)
    job.status = STATUS_FAILED
    job.generation_step = generation_step
    job.error_code = error_code
    job.message = message
    job.active_key = None
    job.lease_expires_at = None
    job.completed_at = timestamp
    job.updated_at = timestamp
    if commit:
        database_session.commit()
    else:
        database_session.flush()


def claim_next_job(
    worker_id: str,
    *,
    lease_seconds: float = 600.0,
    max_attempts: int = 3,
    session=None,
    now: datetime | None = None,
):
    """Claim and commit one pending or stale job without holding its lock."""

    Job, _ = _models()
    database_session = _session(session)
    timestamp = now or datetime.now(UTC)

    while True:
        eligible = or_(
            and_(
                Job.status == STATUS_PENDING,
                Job.available_at <= timestamp,
            ),
            and_(
                Job.status == STATUS_PROCESSING,
                Job.lease_expires_at <= timestamp,
            ),
        )
        query = (
            database_session.query(Job)
            .filter(eligible)
            .order_by(
                case((Job.status == STATUS_PENDING, 0), else_=1),
                Job.available_at.asc(),
                Job.id.asc(),
            )
        )
        if database_session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        job = query.first()
        if job is None:
            database_session.rollback()
            return None

        if (job.attempt_count or 0) >= max_attempts:
            mark_failed(
                job,
                message=MAX_ATTEMPTS_MESSAGE,
                error_code="maximum_attempts_exceeded",
                session=database_session,
                commit=False,
                now=timestamp,
            )
            database_session.commit()
            continue

        mark_processing(
            job,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            now=timestamp,
        )
        database_session.commit()
        return job

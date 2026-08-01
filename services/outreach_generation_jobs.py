"""Queue and lease operations for durable Outreach generation."""

from datetime import UTC, datetime, timedelta
from sqlalchemy import and_, case, or_
from sqlalchemy.exc import IntegrityError
from extensions import db
from app import OutreachGenerationJob


def active_key(organization_id, initiative_id, opportunity_id):
    return f"{organization_id}:{initiative_id}:{opportunity_id}"


def get_active_job(organization_id, initiative_id, opportunity_id, *, session=None):
    session = session or db.session
    return session.query(OutreachGenerationJob).filter_by(
        active_key=active_key(organization_id, initiative_id, opportunity_id)
    ).first()


def get_latest_job(opportunity_id, *, session=None):
    session = session or db.session
    return session.query(OutreachGenerationJob).filter_by(
        opportunity_id=opportunity_id
    ).order_by(OutreachGenerationJob.created_at.desc(), OutreachGenerationJob.id.desc()).first()


def enqueue_job(organization, initiative, opportunity, *, session=None, now=None):
    session = session or db.session
    existing = get_active_job(organization.id, initiative.id, opportunity.id, session=session)
    if existing:
        return existing, False
    timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    job = OutreachGenerationJob(
        opportunity_id=opportunity.id, organization_id=organization.id,
        initiative_id=initiative.id, status="queued",
        active_key=active_key(organization.id, initiative.id, opportunity.id),
        available_at=timestamp, attempt_count=0,
    )
    session.add(job)
    try:
        session.commit()
        return job, True
    except IntegrityError:
        session.rollback()
        winner = get_active_job(organization.id, initiative.id, opportunity.id, session=session)
        if winner is None:
            raise
        return winner, False


def claim_next_job(worker_id, *, lease_seconds=600, max_attempts=3, session=None, now=None):
    session = session or db.session
    timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    while True:
        eligible = or_(
            and_(OutreachGenerationJob.status == "queued", OutreachGenerationJob.available_at <= timestamp),
            and_(OutreachGenerationJob.status == "working", OutreachGenerationJob.lease_expires_at <= timestamp),
        )
        query = session.query(OutreachGenerationJob).filter(eligible).order_by(
            case((OutreachGenerationJob.status == "queued", 0), else_=1),
            OutreachGenerationJob.available_at.asc(), OutreachGenerationJob.id.asc(),
        )
        if session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = query.first()
        if job is None:
            session.rollback(); return None
        if (job.attempt_count or 0) >= max_attempts:
            mark_failed(job, "Outreach generation could not be completed after multiple attempts.", session=session, commit=False, now=timestamp)
            session.commit(); continue
        job.status = "working"; job.worker_id = worker_id
        job.started_at = job.started_at or timestamp
        job.lease_expires_at = timestamp + timedelta(seconds=lease_seconds)
        job.attempt_count = (job.attempt_count or 0) + 1
        session.commit(); return job


def mark_completed(job, *, session=None, commit=True, now=None):
    session = session or db.session; timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    job.status="completed"; job.completed_at=timestamp; job.error_message=None
    job.active_key=None; job.lease_expires_at=None
    session.commit() if commit else session.flush()


def mark_failed(job, message, *, session=None, commit=True, now=None):
    session = session or db.session; timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    job.status="failed"; job.completed_at=timestamp; job.error_message=message
    job.active_key=None; job.lease_expires_at=None
    session.commit() if commit else session.flush()

"""Background lifecycle processing for Contact Discovery jobs."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Callable

from sqlalchemy import and_, case, or_
from sqlalchemy.exc import IntegrityError

from app import ContactResearchJob, Opportunity
from extensions import db
from services.contact_research import (
    ContactResearchError,
    ContactResearchResult,
    research_opportunity_contact,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _active_key(opportunity_id: int) -> str:
    return str(opportunity_id)


def enqueue_contact_research_job(opportunity, *, session=None, now=None):
    """Create or reuse the one active Contact Discovery job."""

    database_session = session or db.session
    key = _active_key(opportunity.id)
    existing = database_session.query(ContactResearchJob).filter_by(
        active_key=key,
    ).first()
    if existing is not None:
        return existing, False

    timestamp = now or _now()
    job = ContactResearchJob(
        opportunity_id=opportunity.id,
        status="queued",
        active_key=key,
        available_at=timestamp,
        attempt_count=0,
    )
    database_session.add(job)
    try:
        database_session.commit()
        return job, True
    except IntegrityError:
        database_session.rollback()
        winner = database_session.query(ContactResearchJob).filter_by(
            active_key=key,
        ).first()
        if winner is None:
            raise
        return winner, False


def claim_next_contact_research_job(
    worker_id="contact-research-worker",
    *,
    lease_seconds=600,
    max_attempts=3,
    session=None,
    now=None,
):
    """Claim one queued job or reclaim one whose processing lease expired."""

    database_session = session or db.session
    timestamp = now or _now()
    eligible = or_(
        and_(
            ContactResearchJob.status == "queued",
            ContactResearchJob.available_at <= timestamp,
        ),
        and_(
            ContactResearchJob.status == "processing",
            or_(
                ContactResearchJob.lease_expires_at.is_(None),
                ContactResearchJob.lease_expires_at <= timestamp,
            ),
        ),
    )
    query = (
        database_session.query(ContactResearchJob)
        .filter(eligible)
        .order_by(
            case((ContactResearchJob.status == "queued", 0), else_=1),
            ContactResearchJob.available_at.asc(),
            ContactResearchJob.id.asc(),
        )
    )
    if database_session.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    while True:
        job = query.first()
        if job is None:
            database_session.rollback()
            return None
        if (job.attempt_count or 0) >= max_attempts:
            job.status = "failed"
            job.error_message = (
                "Contact research could not be completed after multiple attempts."
            )
            job.completed_at = timestamp
            job.active_key = None
            job.worker_id = None
            job.lease_expires_at = None
            database_session.commit()
            continue

        job.status = "processing"
        job.worker_id = worker_id
        job.started_at = job.started_at or timestamp
        job.lease_expires_at = timestamp + timedelta(seconds=lease_seconds)
        job.attempt_count = (job.attempt_count or 0) + 1
        database_session.commit()
        return job


def process_next_contact_research_job(
    *,
    worker_id="contact-research-worker",
    session=None,
    now=None,
    result_factory: Callable = research_opportunity_contact,
) -> bool:
    """Process one queued Contact Discovery job, if available."""

    database_session = session or db.session
    job = claim_next_contact_research_job(
        worker_id,
        session=database_session,
        now=now,
    )
    if job is None:
        return False

    try:
        opportunity = database_session.get(
            Opportunity,
            job.opportunity_id,
        )
        if opportunity is None:
            raise LookupError("The Contact Discovery opportunity was not found.")
        result = ContactResearchResult.model_validate(
            result_factory(opportunity)
        )
        job.result_json = result.model_dump_json()
        if result.result_type.value != "no_contact":
            opportunity.contact_name = result.contact_name
            opportunity.title = result.title
            opportunity.department = result.department
            opportunity.email = result.email
            opportunity.phone = result.phone
            opportunity.contact_url = result.contact_url
            opportunity.linkedin_url = result.linkedin_url
            opportunity.why_this_contact = result.why_this_contact
            opportunity.confidence = result.confidence
            opportunity.verified_date = date.today().isoformat()
            opportunity.sources_json = json.dumps(result.evidence_urls)
        job.status = "completed"
        job.error_message = None
        job.completed_at = now or _now()
        job.active_key = None
        job.worker_id = None
        job.lease_expires_at = None
        database_session.commit()
    except Exception as exc:
        database_session.rollback()
        job = database_session.get(ContactResearchJob, job.id)
        job.status = "failed"
        job.error_message = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, ContactResearchError):
            job.provider_response_id = exc.provider_response_id
            job.input_tokens = exc.input_tokens
            job.output_tokens = exc.output_tokens
        job.completed_at = now or _now()
        job.active_key = None
        job.worker_id = None
        job.lease_expires_at = None
        database_session.commit()

    return True

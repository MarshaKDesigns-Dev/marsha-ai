"""Background lifecycle processing for Contact Discovery jobs."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Callable

from app import ContactResearchJob, Opportunity
from extensions import db
from services.contact_research import (
    ContactResearchError,
    ContactResearchResult,
    research_opportunity_contact,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def claim_next_contact_research_job(*, session=None, now=None):
    """Claim and persist one queued Contact Discovery job."""

    database_session = session or db.session
    query = (
        database_session.query(ContactResearchJob)
        .filter_by(status="queued")
        .order_by(
            ContactResearchJob.created_at.asc(),
            ContactResearchJob.id.asc(),
        )
    )
    if database_session.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    job = query.first()
    if job is None:
        database_session.rollback()
        return None

    job.status = "processing"
    job.started_at = now or _now()
    database_session.commit()
    return job


def process_next_contact_research_job(
    *,
    session=None,
    now=None,
    result_factory: Callable = research_opportunity_contact,
) -> bool:
    """Process one queued Contact Discovery job, if available."""

    database_session = session or db.session
    job = claim_next_contact_research_job(
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
        database_session.commit()

    return True

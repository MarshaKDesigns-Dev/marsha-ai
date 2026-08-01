import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import ContactResearchJob, Opportunity, db
from services.contact_research import (
    ContactResearchError,
    _validate_contact_research_output,
)
from services.contact_research_worker import (
    claim_next_contact_research_job,
    enqueue_contact_research_job,
    process_next_contact_research_job,
)


NOW = datetime(2026, 7, 28, 15, 0, 0)


def test_contact_research_job_has_durable_claim_constraints():
    columns = ContactResearchJob.__table__.c
    assert columns.active_key.unique is True
    assert {index.name for index in ContactResearchJob.__table__.indexes} >= {
        "ix_contact_research_job_claim",
        "ix_contact_research_job_opportunity_created",
    }


@pytest.fixture
def job_session():
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def opportunity_with_jobs(session, *statuses):
    opportunity = Opportunity(parent_prospect="Example Sponsor")
    session.add(opportunity)
    session.flush()
    jobs = [
        ContactResearchJob(
            opportunity_id=opportunity.id,
            status=status,
            available_at=NOW,
        )
        for status in statuses
    ]
    session.add_all(jobs)
    session.commit()
    return opportunity, jobs


def populate_existing_opportunity(opportunity):
    opportunity.contact_name = "Existing Contact"
    opportunity.title = "Existing Title"
    opportunity.department = "Existing Department"
    opportunity.email = "existing@example.org"
    opportunity.phone = "919-555-0199"
    opportunity.contact_url = "https://existing.example/contact"
    opportunity.linkedin_url = "https://linkedin.com/in/existing"
    opportunity.why_this_contact = "Existing verified contact."
    opportunity.confidence = "existing"
    opportunity.verified_date = "2026-07-01"
    opportunity.sources_json = '["https://existing.example/source"]'


def contact_state(opportunity):
    return {
        "contact_name": opportunity.contact_name,
        "title": opportunity.title,
        "department": opportunity.department,
        "email": opportunity.email,
        "phone": opportunity.phone,
        "contact_url": opportunity.contact_url,
        "linkedin_url": opportunity.linkedin_url,
        "why_this_contact": opportunity.why_this_contact,
        "confidence": opportunity.confidence,
        "verified_date": opportunity.verified_date,
        "sources_json": opportunity.sources_json,
    }


def test_queued_job_is_claimed_and_marked_processing(job_session):
    _, jobs = opportunity_with_jobs(job_session, "queued")

    claimed = claim_next_contact_research_job(
        session=job_session,
        now=NOW,
    )

    assert claimed.id == jobs[0].id
    assert claimed.status == "processing"
    assert claimed.started_at == NOW
    assert claimed.worker_id == "contact-research-worker"
    assert claimed.attempt_count == 1
    assert claimed.lease_expires_at == NOW + timedelta(seconds=600)


def test_duplicate_enqueue_reuses_active_job(job_session):
    opportunity = Opportunity(parent_prospect="Example Sponsor")
    job_session.add(opportunity)
    job_session.commit()

    first, created = enqueue_contact_research_job(
        opportunity, session=job_session, now=NOW
    )
    second, duplicate_created = enqueue_contact_research_job(
        opportunity, session=job_session, now=NOW
    )

    assert created is True
    assert duplicate_created is False
    assert second.id == first.id
    assert first.active_key == str(opportunity.id)


def test_expired_processing_job_is_reclaimed_but_active_lease_is_not(job_session):
    opportunity, jobs = opportunity_with_jobs(job_session, "processing", "processing")
    jobs[0].active_key = str(opportunity.id)
    jobs[0].worker_id = "stale-worker"
    jobs[0].attempt_count = 1
    jobs[0].available_at = NOW - timedelta(hours=1)
    jobs[0].lease_expires_at = NOW - timedelta(seconds=1)
    jobs[1].worker_id = "active-worker"
    jobs[1].available_at = NOW - timedelta(hours=1)
    jobs[1].lease_expires_at = NOW + timedelta(seconds=1)
    job_session.commit()

    claimed = claim_next_contact_research_job(
        "replacement-worker", session=job_session, now=NOW
    )

    assert claimed.id == jobs[0].id
    assert claimed.worker_id == "replacement-worker"
    assert claimed.attempt_count == 2
    assert jobs[1].worker_id == "active-worker"


def test_failed_attempt_releases_active_key_and_allows_retry(job_session):
    opportunity = Opportunity(parent_prospect="Example Sponsor")
    job_session.add(opportunity)
    job_session.commit()
    first, _ = enqueue_contact_research_job(
        opportunity, session=job_session, now=NOW
    )

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: (_ for _ in ()).throw(
            RuntimeError("temporary failure")
        ),
    )
    retry, created = enqueue_contact_research_job(
        opportunity, session=job_session, now=NOW + timedelta(minutes=1)
    )

    assert first.status == "failed"
    assert first.active_key is None
    assert first.worker_id is None
    assert first.lease_expires_at is None
    assert created is True
    assert retry.id != first.id


def test_successful_retry_supersedes_failure_without_resetting_workflow(job_session):
    opportunity = Opportunity(
        parent_prospect="Example Sponsor",
        stage="Sent",
        outreach="Existing approved outreach",
        sent_date=NOW.date(),
    )
    populate_existing_opportunity(opportunity)
    job_session.add(opportunity)
    job_session.commit()
    first, _ = enqueue_contact_research_job(
        opportunity, session=job_session, now=NOW
    )
    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: (_ for _ in ()).throw(
            RuntimeError("temporary failure")
        ),
    )
    retry, _ = enqueue_contact_research_job(
        opportunity, session=job_session, now=NOW + timedelta(minutes=1)
    )
    process_next_contact_research_job(
        session=job_session,
        now=NOW + timedelta(minutes=1),
        result_factory=lambda item: {
            "result_type": "general_contact",
            "email": "new-contact@example.org",
            "why_this_contact": "Verified public contact route.",
            "confidence": "high",
            "evidence_urls": ["https://example.org/contact"],
        },
    )

    saved = job_session.get(Opportunity, opportunity.id)
    assert first.status == "failed"
    assert retry.status == "completed"
    assert saved.email == "new-contact@example.org"
    assert saved.stage == "Sent"
    assert saved.outreach == "Existing approved outreach"
    assert saved.sent_date == NOW.date()


def test_successful_job_persists_validated_result(job_session):
    _, jobs = opportunity_with_jobs(job_session, "queued")

    assert process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda opportunity: {
            "result_type": "no_contact",
            "why_this_contact": "No verified public contact was found.",
            "confidence": "low",
            "evidence_urls": [],
        },
    )

    saved = job_session.get(ContactResearchJob, jobs[0].id)
    result = json.loads(saved.result_json)
    assert saved.status == "completed"
    assert saved.completed_at == NOW
    assert saved.error_message is None
    assert result == {
        "contact_name": None,
        "title": None,
        "department": None,
        "email": None,
        "phone": None,
        "contact_url": None,
        "linkedin_url": None,
        "why_this_contact": "No verified public contact was found.",
        "confidence": "low",
        "evidence_urls": [],
        "result_type": "no_contact",
    }


def test_failure_marks_job_failed(job_session):
    _, jobs = opportunity_with_jobs(job_session, "queued")

    assert process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda opportunity: (_ for _ in ()).throw(
            RuntimeError("test failure")
        ),
    )

    saved = job_session.get(ContactResearchJob, jobs[0].id)
    assert saved.status == "failed"
    assert saved.error_message == "RuntimeError: test failure"
    assert saved.completed_at == NOW


def test_provider_metadata_persists_with_contact_research_failure(job_session):
    _, jobs = opportunity_with_jobs(job_session, "queued")

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda opportunity: (_ for _ in ()).throw(
            ContactResearchError(
                "ValidationError: contact_name is required",
                provider_response_id="resp_contact_failure",
                input_tokens=321,
                output_tokens=87,
            )
        ),
    )

    saved = job_session.get(ContactResearchJob, jobs[0].id)
    assert saved.status == "failed"
    assert saved.error_message == (
        "ContactResearchError: ValidationError: contact_name is required"
    )
    assert saved.provider_response_id == "resp_contact_failure"
    assert saved.input_tokens == 321
    assert saved.output_tokens == 87
    assert saved.completed_at == NOW


def test_worker_validation_failure_preserves_full_details(job_session):
    opportunity, jobs = opportunity_with_jobs(job_session, "queued")
    populate_existing_opportunity(opportunity)
    job_session.commit()
    before = contact_state(opportunity)

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda opportunity: {
            "result_type": "named_contact",
            "contact_name": None,
            "why_this_contact": "Unsupported result.",
            "confidence": "low",
            "evidence_urls": [],
        },
    )

    saved = job_session.get(ContactResearchJob, jobs[0].id)
    assert saved.status == "failed"
    assert "ValidationError" in saved.error_message
    assert "A named contact requires contact_name." in saved.error_message
    assert contact_state(job_session.get(Opportunity, opportunity.id)) == before


def test_provider_failure_leaves_every_opportunity_field_unchanged(job_session):
    opportunity, _ = opportunity_with_jobs(job_session, "queued")
    populate_existing_opportunity(opportunity)
    job_session.commit()
    before = contact_state(opportunity)

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: (_ for _ in ()).throw(
            ContactResearchError("APIError: provider unavailable")
        ),
    )

    assert contact_state(job_session.get(Opportunity, opportunity.id)) == before


def test_rejected_evidence_failure_leaves_opportunity_unchanged(job_session):
    opportunity, jobs = opportunity_with_jobs(job_session, "queued")
    populate_existing_opportunity(opportunity)
    job_session.commit()
    before = contact_state(opportunity)
    detailed_error = (
        "ValueError: Contact evidence validation failed. Allowed evidence "
        "policy: every evidence URL must be a public HTTP/HTTPS URL returned "
        "in the provider's web_search_call citations or source list. "
        "Rejected evidence URLs: 'https://example.org/contact': not present "
        "in the provider's web-search citations or source list."
    )

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: (_ for _ in ()).throw(
            ContactResearchError(
                detailed_error,
                provider_response_id="resp_rejected_evidence",
                input_tokens=500,
                output_tokens=200,
            )
        ),
    )

    saved_job = job_session.get(ContactResearchJob, jobs[0].id)
    assert "https://example.org/contact" in saved_job.error_message
    assert saved_job.provider_response_id == "resp_rejected_evidence"
    assert saved_job.input_tokens == 500
    assert saved_job.output_tokens == 200
    assert contact_state(job_session.get(Opportunity, opportunity.id)) == before


def test_completed_job_is_not_processed_again(job_session):
    _, jobs = opportunity_with_jobs(job_session, "completed")

    assert not process_next_contact_research_job(
        session=job_session,
        now=NOW,
    )
    assert job_session.get(ContactResearchJob, jobs[0].id).status == "completed"


def test_one_processing_call_claims_only_one_queued_job(job_session):
    _, jobs = opportunity_with_jobs(job_session, "queued", "queued")

    assert process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda opportunity: {
            "result_type": "no_contact",
            "why_this_contact": "No verified public contact was found.",
            "confidence": "low",
            "evidence_urls": [],
        },
    )

    statuses = [
        job_session.get(ContactResearchJob, job.id).status
        for job in jobs
    ]
    assert statuses == ["completed", "queued"]


def test_named_contact_and_evidence_persist_to_opportunity(job_session):
    opportunity, jobs = opportunity_with_jobs(job_session, "queued")

    assert process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: {
            "result_type": "named_contact",
            "contact_name": "Jordan Lee",
            "title": "Partnerships Director",
            "department": "Community Partnerships",
            "email": "jordan@example.org",
            "phone": "919-555-0100",
            "contact_url": "https://example.org/contact",
            "linkedin_url": "https://linkedin.com/in/jordan-lee",
            "why_this_contact": "Officially listed partnerships contact.",
            "confidence": "high",
            "evidence_urls": ["https://example.org/contact"],
        },
    )

    saved = job_session.get(Opportunity, opportunity.id)
    assert saved.contact_name == "Jordan Lee"
    assert saved.title == "Partnerships Director"
    assert saved.department == "Community Partnerships"
    assert saved.email == "jordan@example.org"
    assert saved.phone == "919-555-0100"
    assert saved.contact_url == "https://example.org/contact"
    assert saved.linkedin_url == "https://linkedin.com/in/jordan-lee"
    assert saved.why_this_contact == "Officially listed partnerships contact."
    assert saved.confidence == "high"
    assert saved.verified_date
    assert json.loads(saved.sources_json) == ["https://example.org/contact"]
    assert job_session.get(ContactResearchJob, jobs[0].id).status == "completed"


def test_general_contact_persists_to_opportunity(job_session):
    opportunity, _ = opportunity_with_jobs(job_session, "queued")

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: {
            "result_type": "general_contact",
            "email": "partnerships@example.org",
            "contact_url": "https://example.org/partnerships",
            "why_this_contact": "Official partnerships route.",
            "confidence": "medium",
            "evidence_urls": ["https://example.org/partnerships"],
        },
    )

    saved = job_session.get(Opportunity, opportunity.id)
    assert saved.contact_name is None
    assert saved.email == "partnerships@example.org"
    assert saved.contact_url == "https://example.org/partnerships"


def test_general_contact_persists_after_organization_name_normalization(
    job_session,
):
    opportunity, jobs = opportunity_with_jobs(job_session, "queued")
    opportunity.parent_prospect = "Example Sponsor"
    job_session.commit()
    provider_output = json.dumps(
        {
            "result_type": "general_contact",
            "contact_name": "EXAMPLE SPONSOR",
            "department": "General Inquiries",
            "contact_url": "https://example.org/contact",
            "why_this_contact": "Official general contact page.",
            "confidence": "high",
            "evidence_urls": ["https://example.org/contact"],
        }
    )

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: _validate_contact_research_output(
            provider_output,
            sponsor_name=item.parent_prospect,
        ),
    )

    saved = job_session.get(Opportunity, opportunity.id)
    saved_job = job_session.get(ContactResearchJob, jobs[0].id)
    assert saved_job.status == "completed"
    assert saved.contact_name is None
    assert saved.department == "General Inquiries"
    assert saved.contact_url == "https://example.org/contact"
    assert saved.verified_date


def test_reconciled_general_contact_persists_successfully(job_session):
    opportunity, jobs = opportunity_with_jobs(job_session, "queued")
    contact_url = (
        "https://example.org/contact/?utm_source=openai&ref=directory"
    )
    provider_output = json.dumps(
        {
            "result_type": "general_contact",
            "contact_url": contact_url,
            "why_this_contact": "Official general contact page.",
            "confidence": "high",
            "evidence_urls": [""],
        }
    )

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: _validate_contact_research_output(
            provider_output,
            sponsor_name=item.parent_prospect,
            cited_urls_exact={contact_url},
        ),
    )

    saved = job_session.get(Opportunity, opportunity.id)
    saved_job = job_session.get(ContactResearchJob, jobs[0].id)
    assert saved_job.status == "completed"
    assert saved.contact_url == contact_url
    assert json.loads(saved.sources_json) == [contact_url]
    assert saved.verified_date


def test_no_contact_result_leaves_opportunity_unchanged(job_session):
    opportunity, _ = opportunity_with_jobs(job_session, "queued")
    populate_existing_opportunity(opportunity)
    job_session.commit()
    before = contact_state(opportunity)

    process_next_contact_research_job(
        session=job_session,
        now=NOW,
        result_factory=lambda item: {
            "result_type": "no_contact",
            "why_this_contact": "No verified public contact was found.",
            "confidence": "low",
            "evidence_urls": [],
        },
    )

    saved = job_session.get(Opportunity, opportunity.id)
    assert contact_state(saved) == before

"""Process durable Outreach generation jobs."""

from app import (
    Opportunity, Organization, SponsorProspect, SponsorshipInitiative,
    determine_outreach_channel, draft_outreach, validate_outreach_readiness,
)
from extensions import db
from services.outreach_generation_jobs import claim_next_job, mark_completed, mark_failed


SAFE_FAILURE = "The Outreach Worker could not prepare this message. Your Opportunity and contact data were preserved."


def _context(organization, initiative):
    return {
        "organization_name": organization.name or "Organization",
        "organization_type": organization.organization_type or "Organization",
        "location": organization.location or "", "mission": organization.mission or "",
        "sender_name": organization.sender_name or "", "sender_title": organization.sender_title or "",
        "sender_email": organization.sender_email or "", "website": organization.website or "",
        "organization_phone": organization.phone or "", "initiative_name": initiative.name or "",
        "fundraising_target": initiative.fundraising_target or "", "deadline": initiative.deadline or "",
        "audience": initiative.audience or "", "needs": initiative.needs or "", "goals": initiative.goals or "",
    }


def process_next_outreach_generation_job(*, worker_id, lease_seconds=600, max_attempts=3,
                                         claim=claim_next_job, draft=draft_outreach):
    job = claim(worker_id, lease_seconds=lease_seconds, max_attempts=max_attempts)
    if job is None:
        return False
    job_id = job.id
    try:
        opportunity = db.session.get(Opportunity, job.opportunity_id)
        organization = db.session.get(Organization, job.organization_id)
        initiative = db.session.get(SponsorshipInitiative, job.initiative_id)
        if not opportunity or not organization or not initiative or opportunity.outreach:
            raise ValueError("Outreach generation is no longer available.")
        prospect_record = db.session.get(SponsorProspect, opportunity.sponsor_prospect_id)
        prospect = {
            "name": opportunity.recommended_target or opportunity.parent_prospect or "",
            "category": opportunity.category or "",
            "fit": getattr(prospect_record, "why_fits", "") or "",
            "angle": getattr(prospect_record, "recommended_ask", None) or getattr(prospect_record, "why_recommended", None) or "",
        }
        contact = {
            "recommended_target": opportunity.recommended_target, "contact_name": opportunity.contact_name,
            "title": opportunity.title, "department": opportunity.department, "email": opportunity.email,
            "phone": opportunity.phone, "contact_url": opportunity.contact_url,
            "why_this_contact": opportunity.why_this_contact, "sources": opportunity.sources,
        }
        outreach = draft(prospect, contact, worker_context=_context(organization, initiative))
        errors = validate_outreach_readiness(contact, outreach)
        if outreach.startswith(("OPENAI_API_KEY is not configured.", "Outreach drafting failed:")):
            errors.append(outreach)
        if errors:
            raise ValueError(SAFE_FAILURE)
        opportunity.outreach = outreach
        opportunity.outreach_channel = determine_outreach_channel(contact)
        opportunity.message_approved_at = None
        if opportunity.outreach_channel == "email" and not opportunity.subject:
            opportunity.subject = f"Potential partnership with {organization.name}"
        opportunity.stage = "Ready to Send"
        mark_completed(job, session=db.session, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        job = db.session.get(type(job), job_id)
        mark_failed(job, SAFE_FAILURE)
    return True

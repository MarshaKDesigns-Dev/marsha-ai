"""Process durable Follow-Up generation jobs."""
from app import Opportunity, Organization, SponsorshipInitiative, apply_follow_up_draft, draft_follow_up
from extensions import db
from services.follow_up_generation_jobs import claim_next_job, mark_completed, mark_failed
SAFE_FAILURE="The Follow-Up Worker could not prepare this follow-up. Your original outreach, delivery history, and Opportunity data were preserved."
def _context(org,init):
    return {"organization_name":org.name or "Organization","organization_type":org.organization_type or "Organization","location":org.location or "","mission":org.mission or "","sender_name":org.sender_name or "","sender_title":org.sender_title or "","sender_email":org.sender_email or "","website":org.website or "","organization_phone":org.phone or "","initiative_name":init.name or "","fundraising_target":init.fundraising_target or "","deadline":init.deadline or "","audience":init.audience or "","needs":init.needs or "","goals":init.goals or ""}
def process_next_follow_up_generation_job(*,worker_id,lease_seconds=600,max_attempts=3,claim=claim_next_job,draft=draft_follow_up):
    job=claim(worker_id,lease_seconds=lease_seconds,max_attempts=max_attempts)
    if job is None:return False
    job_id=job.id
    try:
        opp=db.session.get(Opportunity,job.opportunity_id)
        org=db.session.get(Organization,job.organization_id);init=db.session.get(SponsorshipInitiative,job.initiative_id)
        if opp is None or org is None or init is None:raise ValueError("Opportunity unavailable")
        result=draft(opp,worker_context=_context(org,init))
        if result.get("error"):raise ValueError(SAFE_FAILURE)
        apply_follow_up_draft(opp,result)
        mark_completed(job,session=db.session,commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback();job=db.session.get(type(job),job_id);mark_failed(job,SAFE_FAILURE)
    return True

"""Durable queue operations for Follow-Up generation."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import and_, case, or_
from sqlalchemy.exc import IntegrityError
from app import FollowUpGenerationJob
from extensions import db
def active_key(org, init, opp): return f"{org}:{init}:{opp}"
def get_active_job(org, init, opp, *, session=None):
    s=session or db.session
    return s.query(FollowUpGenerationJob).filter_by(active_key=active_key(org,init,opp)).first()
def get_latest_job(opp, *, session=None):
    s=session or db.session
    return s.query(FollowUpGenerationJob).filter_by(opportunity_id=opp).order_by(FollowUpGenerationJob.created_at.desc(),FollowUpGenerationJob.id.desc()).first()
def enqueue_job(org, init, opp, *, session=None, now=None):
    s=session or db.session; existing=get_active_job(org.id,init.id,opp.id,session=s)
    if existing:return existing,False
    stamp=(now or datetime.now(UTC)).replace(tzinfo=None)
    job=FollowUpGenerationJob(opportunity_id=opp.id,organization_id=org.id,initiative_id=init.id,status="queued",active_key=active_key(org.id,init.id,opp.id),available_at=stamp,attempt_count=0)
    s.add(job)
    try:s.commit();return job,True
    except IntegrityError:
        s.rollback(); winner=get_active_job(org.id,init.id,opp.id,session=s)
        if winner is None:raise
        return winner,False
def claim_next_job(worker_id,*,lease_seconds=600,max_attempts=3,session=None,now=None):
    s=session or db.session; stamp=(now or datetime.now(UTC)).replace(tzinfo=None)
    while True:
        eligible=or_(and_(FollowUpGenerationJob.status=="queued",FollowUpGenerationJob.available_at<=stamp),and_(FollowUpGenerationJob.status=="working",FollowUpGenerationJob.lease_expires_at<=stamp))
        q=s.query(FollowUpGenerationJob).filter(eligible).order_by(case((FollowUpGenerationJob.status=="queued",0),else_=1),FollowUpGenerationJob.available_at.asc(),FollowUpGenerationJob.id.asc())
        if s.get_bind().dialect.name=="postgresql":q=q.with_for_update(skip_locked=True)
        job=q.first()
        if job is None:s.rollback();return None
        if (job.attempt_count or 0)>=max_attempts:
            mark_failed(job,"Follow-Up generation could not be completed after multiple attempts.",session=s,commit=False,now=stamp);s.commit();continue
        job.status="working";job.worker_id=worker_id;job.started_at=job.started_at or stamp;job.lease_expires_at=stamp+timedelta(seconds=lease_seconds);job.attempt_count=(job.attempt_count or 0)+1;s.commit();return job
def mark_completed(job,*,session=None,commit=True,now=None):
    s=session or db.session;stamp=(now or datetime.now(UTC)).replace(tzinfo=None);job.status="completed";job.completed_at=stamp;job.error_message=None;job.active_key=None;job.lease_expires_at=None;s.commit() if commit else s.flush()
def mark_failed(job,message,*,session=None,commit=True,now=None):
    s=session or db.session;stamp=(now or datetime.now(UTC)).replace(tzinfo=None);job.status="failed";job.completed_at=stamp;job.error_message=message;job.active_key=None;job.lease_expires_at=None;s.commit() if commit else s.flush()

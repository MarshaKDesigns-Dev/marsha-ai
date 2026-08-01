from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from app import OutreachGenerationJob
from services import outreach_generation_jobs as jobs

NOW=datetime(2026,7,31,12)
def query(*values):
 q=MagicMock(); q.filter_by.return_value=q; q.filter.return_value=q; q.order_by.return_value=q; q.with_for_update.return_value=q; q.first.side_effect=values; return q

def test_model_constraints_and_indexes():
 assert OutreachGenerationJob.__table__.c.active_key.unique is True
 assert {i.name for i in OutreachGenerationJob.__table__.indexes} >= {"ix_outreach_generation_claim","ix_outreach_generation_history"}
 assert "ck_outreach_generation_job_status" in {c.name for c in OutreachGenerationJob.__table__.constraints}

def test_enqueue_and_duplicate_reuse():
 org=SimpleNamespace(id=1); init=SimpleNamespace(id=2); opp=SimpleNamespace(id=3)
 session=MagicMock(); session.query.return_value=query(None)
 job,created=jobs.enqueue_job(org,init,opp,session=session,now=NOW)
 assert created and job.status=="queued" and job.active_key=="1:2:3" and job.worker_id is None
 existing=MagicMock(); existing.query.return_value=query(job)
 assert jobs.enqueue_job(org,init,opp,session=existing)[1] is False

def test_claim_lease_reclaim_and_terminal_release():
 job=OutreachGenerationJob(id=1,status="queued",active_key="1:2:3",available_at=NOW,attempt_count=0)
 session=MagicMock(); session.query.return_value=query(job); session.get_bind.return_value.dialect.name="sqlite"
 assert jobs.claim_next_job("worker",session=session,now=NOW,lease_seconds=300) is job
 assert job.status=="working" and job.worker_id=="worker" and job.attempt_count==1
 assert job.lease_expires_at==NOW+timedelta(seconds=300)
 jobs.mark_completed(job,session=session,now=NOW)
 assert job.status=="completed" and job.active_key is None and job.lease_expires_at is None

def test_failed_job_releases_key():
 job=OutreachGenerationJob(status="working",active_key="1:2:3",lease_expires_at=NOW)
 session=MagicMock(); jobs.mark_failed(job,"Safe error",session=session,now=NOW)
 assert job.status=="failed" and job.error_message=="Safe error" and job.active_key is None

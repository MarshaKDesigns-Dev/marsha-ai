from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from app import FollowUpGenerationJob
from services import follow_up_generation_jobs as jobs
NOW=datetime(2026,7,31,12)
def q(*v):
 x=MagicMock();x.filter_by.return_value=x;x.filter.return_value=x;x.order_by.return_value=x;x.with_for_update.return_value=x;x.first.side_effect=v;return x
def test_model_constraints_indexes_and_enqueue():
 assert FollowUpGenerationJob.__table__.c.active_key.unique
 assert {i.name for i in FollowUpGenerationJob.__table__.indexes}>={"ix_follow_up_generation_claim","ix_follow_up_generation_history"}
 s=MagicMock();s.query.return_value=q(None);o=SimpleNamespace(id=1);i=SimpleNamespace(id=2);p=SimpleNamespace(id=3)
 job,created=jobs.enqueue_job(o,i,p,session=s,now=NOW)
 assert created and job.status=="queued" and job.active_key=="1:2:3" and job.worker_id is None
def test_claim_and_terminal_release():
 job=FollowUpGenerationJob(id=1,status="queued",active_key="1:2:3",available_at=NOW,attempt_count=0)
 s=MagicMock();s.query.return_value=q(job);s.get_bind.return_value.dialect.name="sqlite"
 jobs.claim_next_job("w",session=s,now=NOW,lease_seconds=300)
 assert job.status=="working" and job.worker_id=="w" and job.attempt_count==1 and job.lease_expires_at==NOW+timedelta(seconds=300)
 jobs.mark_completed(job,session=s,now=NOW);assert job.active_key is None and job.lease_expires_at is None
def test_failure_releases_key():
 job=FollowUpGenerationJob(status="working",active_key="1:2:3",lease_expires_at=NOW);s=MagicMock();jobs.mark_failed(job,"safe",session=s,now=NOW)
 assert job.status=="failed" and job.active_key is None and job.error_message=="safe"

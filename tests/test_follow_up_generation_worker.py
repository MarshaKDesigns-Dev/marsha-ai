from types import SimpleNamespace
from unittest.mock import MagicMock
import services.follow_up_generation_worker as worker
def test_worker_persists_once_and_completes(monkeypatch):
 job=SimpleNamespace(id=1,opportunity_id=2,organization_id=3,initiative_id=4);opp=SimpleNamespace()
 org=SimpleNamespace(name="Org",organization_type="",location="",mission="",sender_name="",sender_title="",sender_email="",website="",phone="");init=SimpleNamespace(name="I",fundraising_target="",deadline="",audience="",needs="",goals="")
 fake=SimpleNamespace(get=MagicMock(side_effect=[opp,org,init]),commit=MagicMock(),rollback=MagicMock(),flush=MagicMock());monkeypatch.setattr(worker,"db",SimpleNamespace(session=fake))
 apply=MagicMock();done=MagicMock();monkeypatch.setattr(worker,"apply_follow_up_draft",apply);monkeypatch.setattr(worker,"mark_completed",done)
 assert worker.process_next_follow_up_generation_job(worker_id="w",claim=lambda *a,**k:job,draft=lambda o,**k:{"subject":"S","message":"M"})
 apply.assert_called_once();done.assert_called_once_with(job,session=fake,commit=False)
def test_failure_is_sanitized_and_preserves_opportunity(monkeypatch):
 job=SimpleNamespace(id=1,opportunity_id=2,organization_id=3,initiative_id=4);opp=SimpleNamespace(outreach="Original",sent_date="date",follow_up_message=None)
 org=SimpleNamespace(name="Org",organization_type="",location="",mission="",sender_name="",sender_title="",sender_email="",website="",phone="");init=SimpleNamespace(name="I",fundraising_target="",deadline="",audience="",needs="",goals="")
 fake=SimpleNamespace(get=MagicMock(side_effect=[opp,org,init,job]),commit=MagicMock(),rollback=MagicMock());monkeypatch.setattr(worker,"db",SimpleNamespace(session=fake))
 failed=MagicMock();monkeypatch.setattr(worker,"mark_failed",failed)
 worker.process_next_follow_up_generation_job(worker_id="w",claim=lambda *a,**k:job,draft=lambda o,**k:{"error":"secret"})
 assert opp.outreach=="Original" and opp.follow_up_message is None;failed.assert_called_once_with(job,worker.SAFE_FAILURE)

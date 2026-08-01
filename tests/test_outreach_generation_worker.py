from types import SimpleNamespace
from unittest.mock import MagicMock
import services.outreach_generation_worker as worker

def test_worker_persists_draft_and_completes_atomically(monkeypatch):
 job=SimpleNamespace(id=1,opportunity_id=3,organization_id=1,initiative_id=2)
 opp=SimpleNamespace(id=3,outreach=None,sponsor_prospect_id=None,recommended_target="Sponsor",parent_prospect="Sponsor",category="Bank",contact_name="A",title="B",department="C",email="a@b.com",phone=None,contact_url=None,why_this_contact="verified",sources=[],message_approved_at=None,subject=None,stage="Research Approved")
 org=SimpleNamespace(name="Org",organization_type="Nonprofit",location="NC",mission="M",sender_name="S",sender_title="T",sender_email="s@o.org",website="",phone="")
 init=SimpleNamespace(name="Initiative",fundraising_target="$1",deadline="",audience="Adults",needs="Support",goals="Impact")
 fake=SimpleNamespace(get=MagicMock(side_effect=[opp,org,init,None]),commit=MagicMock(),rollback=MagicMock(),flush=MagicMock())
 monkeypatch.setattr(worker,"db",SimpleNamespace(session=fake))
 monkeypatch.setattr(worker,"validate_outreach_readiness",lambda *a: [])
 monkeypatch.setattr(worker,"determine_outreach_channel",lambda c:"email")
 complete=MagicMock(); monkeypatch.setattr(worker,"mark_completed",complete)
 assert worker.process_next_outreach_generation_job(worker_id="w",claim=lambda *a,**k:job,draft=lambda *a,**k:"Draft")
 assert opp.outreach=="Draft" and opp.stage=="Ready to Send"
 complete.assert_called_once_with(job,session=fake,commit=False)

def test_failure_preserves_opportunity(monkeypatch):
 job=SimpleNamespace(id=1,opportunity_id=3,organization_id=1,initiative_id=2)
 opp=SimpleNamespace(outreach=None,sponsor_prospect_id=None,recommended_target="Sponsor",parent_prospect="Sponsor",category="Bank",contact_name="A",title="B",department="C",email="a@b.com",phone=None,contact_url=None,why_this_contact="v",sources=[],subject=None,stage="Research Approved")
 org=SimpleNamespace(name="Org",organization_type="",location="",mission="",sender_name="",sender_title="",sender_email="",website="",phone="")
 init=SimpleNamespace(name="I",fundraising_target="",deadline="",audience="",needs="",goals="")
 fake=SimpleNamespace(get=MagicMock(side_effect=[opp,org,init,None,job]),commit=MagicMock(),rollback=MagicMock())
 monkeypatch.setattr(worker,"db",SimpleNamespace(session=fake))
 failed=MagicMock(); monkeypatch.setattr(worker,"mark_failed",failed)
 worker.process_next_outreach_generation_job(worker_id="w",claim=lambda *a,**k:job,draft=lambda *a,**k:(_ for _ in ()).throw(RuntimeError("secret")))
 assert opp.outreach is None and opp.subject is None and opp.stage=="Research Approved"
 failed.assert_called_once_with(job,worker.SAFE_FAILURE)

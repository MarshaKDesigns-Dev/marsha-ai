from types import SimpleNamespace
from unittest.mock import MagicMock

import services.sponsor_research_worker as worker
from services.sponsor_research import NoCredibleProspectsError


def context(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=2)
    asset = SimpleNamespace(id=3)
    intelligence = SimpleNamespace(sponsor_eligibility=object())
    fake_session = SimpleNamespace(
        get=MagicMock(side_effect=[organization, initiative, asset]),
        rollback=MagicMock(),
    )
    monkeypatch.setattr(worker, "db", SimpleNamespace(session=fake_session))
    monkeypatch.setattr(
        worker, "get_sponsorship_intelligence", lambda *args: intelligence
    )
    query = MagicMock()
    query.filter_by.return_value.all.return_value = []
    monkeypatch.setattr(worker, "SponsorProspect", SimpleNamespace(query=query))


def test_worker_processes_claimed_assignment_to_completion(monkeypatch):
    context(monkeypatch)
    assignment = SimpleNamespace(
        id=4, organization_id=1, initiative_id=2, sponsorship_asset_id=3
    )
    candidate = SimpleNamespace(model_dump=lambda **kwargs: {"name": "Sponsor"})
    complete = MagicMock()
    monkeypatch.setattr(worker, "mark_completed", complete)
    assert worker.process_next_sponsor_research_assignment(
        worker_id="worker-1",
        claim=MagicMock(return_value=assignment),
        research=MagicMock(return_value=[candidate]),
    ) is True
    complete.assert_called_once_with(assignment, [candidate])


def test_controlled_failure_marks_needs_attention_without_partial_results(
    monkeypatch,
):
    context(monkeypatch)
    assignment = SimpleNamespace(
        id=4, organization_id=1, initiative_id=2, sponsorship_asset_id=3
    )
    worker.db.session.get = MagicMock(
        side_effect=[SimpleNamespace(id=1), SimpleNamespace(id=2),
                     SimpleNamespace(id=3), assignment]
    )
    monkeypatch.setattr(
        worker, "get_sponsorship_intelligence",
        lambda *args: SimpleNamespace(sponsor_eligibility=object()),
    )
    failed = MagicMock()
    monkeypatch.setattr(worker, "mark_needs_attention", failed)
    research = MagicMock(
        side_effect=NoCredibleProspectsError("No credible sponsors found.")
    )
    assert worker.process_next_sponsor_research_assignment(
        worker_id="worker-1", claim=MagicMock(return_value=assignment),
        research=research,
    ) is True
    failed.assert_called_once_with(assignment, "No credible sponsors found.")

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from app import (
    SponsorResearchCandidateDiagnostic,
    SponsorResearchDiagnostic,
)
from services.sponsor_research import (
    collect_web_search_queries,
    SponsorResearchResult,
    validate_researched_prospects,
)
from services.sponsor_research_diagnostics import (
    persist_sponsor_research_diagnostics,
    safely_persist_sponsor_research_diagnostics,
)
from tests.test_sponsor_research import candidate, eligibility


def test_models_have_safe_fields_foreign_keys_and_history_indexes():
    parent = SponsorResearchDiagnostic.__table__
    child = SponsorResearchCandidateDiagnostic.__table__
    assert "research_assignment.id" in {
        fk.target_fullname for fk in parent.c.research_assignment_id.foreign_keys
    }
    assert "sponsor_research_diagnostic.id" in {
        fk.target_fullname for fk in child.c.diagnostic_id.foreign_keys
    }
    assert "ix_sponsor_research_diagnostic_assignment_history" in {
        item.name for item in parent.indexes
    }
    assert "ix_sponsor_research_candidate_diagnostic_history" in {
        item.name for item in child.indexes
    }
    assert "prompt" not in parent.c
    assert "raw_response" not in parent.c


def test_provider_search_queries_are_collected_without_page_content():
    response = SimpleNamespace(model_dump=lambda **kwargs: {
        "output": [{
            "type": "web_search_call",
            "action": {
                "query": "award vendors North Carolina",
                "sources": [{"url": "https://example.com", "content": "ignore"}],
            },
        }]
    })
    assert collect_web_search_queries(response) == [
        "award vendors North Carolina"
    ]


def test_validation_records_all_reasons_and_deduplication():
    first = candidate(name="First")
    duplicate = candidate(name="Second", mission_score=20)
    diagnostics = []
    accepted = validate_researched_prospects(
        SponsorResearchResult(prospects=[first, duplicate]),
        cited_urls={"https://example.com/community"},
        eligibility=eligibility(),
        candidate_diagnostics=diagnostics,
    )
    assert accepted == [duplicate]
    assert diagnostics[0]["rejection_codes"] == [
        "duplicate_canonical_website"
    ]
    assert diagnostics[0]["deduplication_result"] == "duplicate_removed"
    assert diagnostics[1]["result_status"] == "accepted"


def test_validation_records_citation_eligibility_and_exact_asset_mismatch():
    prospect = candidate(industry="Alcohol and Brewery")
    diagnostics = []
    asset = SimpleNamespace(name="Exact Approved Asset")
    validate_researched_prospects(
        SponsorResearchResult(prospects=[prospect]),
        cited_urls={"https://different.example/source"},
        eligibility=eligibility("Middle school students"),
        organization=SimpleNamespace(
            current_sponsors_json="[]", existing_relationships_json="[]",
            businesses_already_contacted_json="[]",
            businesses_never_contact_json="[]", mission="", location="",
            organization_type="",
        ),
        initiative=SimpleNamespace(sponsorship_needs_json='["Marketing"]'),
        assets=[asset], selected_asset=asset,
        candidate_diagnostics=diagnostics,
    )
    codes = diagnostics[0]["rejection_codes"]
    assert "evidence_url_not_in_provider_sources" in codes
    assert "prohibited_industry" in codes
    assert "selected_asset_exact_name_mismatch" in codes
    assert diagnostics[0]["citation_validation"]["failed_evidence_urls"]


def test_persistence_stores_only_safe_snapshot_fields():
    session = MagicMock()
    session.flush.side_effect = lambda: None
    assignment = SimpleNamespace(
        id=1, organization_id=2, initiative_id=3, sponsorship_asset_id=4
    )
    snapshot = {
        "provider_response_id": "resp_safe",
        "outcome_code": "candidates_failed_validation",
        "search_queries": ["award vendors North Carolina"],
        "source_urls": ["https://vendor.example"],
        "candidate_count": 1, "accepted_count": 0, "rejected_count": 1,
        "input_tokens": 10, "output_tokens": 20,
        "prompt": "must not persist", "raw_response": "must not persist",
        "candidates": [{
            "candidate_name": "Vendor", "canonical_website": "https://vendor.example",
            "industry": "Awards", "result_status": "rejected",
            "rejection_codes": ["approved_asset_mismatch"],
            "deduplication_result": "not_duplicate", "evidence_urls": [],
        }],
    }
    parent = persist_sponsor_research_diagnostics(
        assignment, snapshot, session=session
    )
    assert parent.provider_response_id == "resp_safe"
    assert parent.outcome_code == "candidates_failed_validation"
    assert json.loads(parent.search_queries_json) == [
        "award vendors North Carolina"
    ]
    assert not hasattr(parent, "prompt")
    assert not hasattr(parent, "raw_response")
    session.commit.assert_called_once()


def test_persistence_failure_is_isolated(monkeypatch):
    import services.sponsor_research_diagnostics as diagnostics
    monkeypatch.setattr(
        diagnostics, "persist_sponsor_research_diagnostics",
        MagicMock(side_effect=RuntimeError("database unavailable")),
    )
    diagnostics.db.session.rollback = MagicMock()
    assert safely_persist_sponsor_research_diagnostics(
        SimpleNamespace(id=1), {"candidate_count": 0}
    ) is False
    diagnostics.db.session.rollback.assert_called_once()


def test_cli_report_separates_accepted_and_rejected(monkeypatch):
    import inspect_sponsor_research as cli

    assignment = SimpleNamespace(
        id=7, status="needs_attention", sponsorship_asset_id=9
    )
    diagnostic = SimpleNamespace(
        id=11, provider_response_id="resp_11",
        outcome_code="candidates_failed_validation",
        search_queries_json='["awards NC"]',
        source_urls_json='["https://source.example"]',
        candidate_count=2, accepted_count=1, rejected_count=1,
    )
    candidates = [
        SimpleNamespace(
            candidate_name="Accepted Vendor", result_status="accepted",
            canonical_website="https://accepted.example",
            rejection_codes_json="[]", citation_validation_json="{}",
        ),
        SimpleNamespace(
            candidate_name="Rejected Vendor", result_status="rejected",
            canonical_website="https://rejected.example",
            rejection_codes_json='["approved_asset_mismatch"]',
            citation_validation_json="{}",
        ),
    ]
    def query(first=None, all_rows=None):
        value = MagicMock()
        value.filter_by.return_value = value
        value.order_by.return_value = value
        value.first.return_value = first
        value.all.return_value = all_rows or []
        return value
    with cli.app.app_context():
        monkeypatch.setattr(cli.ResearchAssignment, "query", query(first=assignment))
        monkeypatch.setattr(
            cli.SponsorshipAsset, "query",
            query(first=SimpleNamespace(name="Awards Sponsor")),
        )
        monkeypatch.setattr(
            cli.SponsorResearchDiagnostic, "query", query(all_rows=[diagnostic])
        )
        monkeypatch.setattr(
            cli.SponsorResearchCandidateDiagnostic, "query",
            query(all_rows=candidates),
        )
        report, status = cli.build_report(7)
    assert status == 0
    assert "[ACCEPTED] Accepted Vendor" in report
    assert "[REJECTED] Rejected Vendor" in report
    assert "approved_asset_mismatch" in report


def test_cli_missing_assignment_is_controlled(monkeypatch):
    import inspect_sponsor_research as cli
    query = MagicMock()
    query.filter_by.return_value.first.return_value = None
    with cli.app.app_context():
        monkeypatch.setattr(cli.ResearchAssignment, "query", query)
        report, status = cli.build_report(404)
    assert status == 2
    assert report == "Research assignment 404 was not found."

"""Safe persistence helpers for Sponsor Research audit diagnostics."""

from __future__ import annotations

import json
import logging
from typing import Any

from app import (
    SponsorResearchCandidateDiagnostic,
    SponsorResearchDiagnostic,
)
from extensions import db


logger = logging.getLogger(__name__)


def persist_sponsor_research_diagnostics(
    assignment: Any,
    snapshot: dict[str, Any] | None,
    *,
    session=None,
) -> SponsorResearchDiagnostic | None:
    """Persist one safe snapshot without retaining prompts or raw responses."""

    if not snapshot:
        return None
    database_session = session or db.session
    diagnostic = SponsorResearchDiagnostic(
        research_assignment_id=assignment.id,
        organization_id=assignment.organization_id,
        initiative_id=assignment.initiative_id,
        sponsorship_asset_id=assignment.sponsorship_asset_id,
        provider_response_id=snapshot.get("provider_response_id"),
        outcome_code=snapshot.get("outcome_code"),
        search_queries_json=json.dumps(snapshot.get("search_queries", [])),
        source_urls_json=json.dumps(snapshot.get("source_urls", [])),
        candidate_count=snapshot.get("candidate_count", 0),
        accepted_count=snapshot.get("accepted_count", 0),
        rejected_count=snapshot.get("rejected_count", 0),
        input_tokens=snapshot.get("input_tokens"),
        output_tokens=snapshot.get("output_tokens"),
    )
    database_session.add(diagnostic)
    database_session.flush()
    for item in snapshot.get("candidates", []):
        database_session.add(
            SponsorResearchCandidateDiagnostic(
                diagnostic_id=diagnostic.id,
                candidate_name=item.get("candidate_name") or "Unknown company",
                canonical_website=item.get("canonical_website"),
                industry=item.get("industry"),
                result_status=item.get("result_status", "rejected"),
                rejection_codes_json=json.dumps(
                    item.get("rejection_codes", [])
                ),
                citation_validation_json=json.dumps(
                    item.get("citation_validation", {})
                ),
                eligibility_result_json=json.dumps(
                    item.get("eligibility_result", {})
                ),
                preference_result_json=json.dumps(
                    item.get("preference_result", {})
                ),
                approved_asset_match=item.get("approved_asset_match"),
                approved_need_match=item.get("approved_need_match"),
                deduplication_result=item.get(
                    "deduplication_result", "not_duplicate"
                ),
                evidence_urls_json=json.dumps(item.get("evidence_urls", [])),
            )
        )
    database_session.commit()
    return diagnostic


def safely_persist_sponsor_research_diagnostics(assignment, snapshot) -> bool:
    """Isolate diagnostic storage failures from the primary research result."""

    try:
        persist_sponsor_research_diagnostics(assignment, snapshot)
        return True
    except Exception:
        db.session.rollback()
        logger.exception(
            "sponsor_research_diagnostic_persistence_failed assignment_id=%s",
            getattr(assignment, "id", None),
        )
        return False

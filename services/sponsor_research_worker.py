"""Process durable Sponsor Research assignments."""

from __future__ import annotations

import logging

from app import (
    Organization,
    SponsorProspect,
    SponsorshipAsset,
    SponsorshipInitiative,
    get_sponsorship_intelligence,
)
from extensions import db
from services.research_assignments import (
    SAFE_FAILURE_MESSAGE,
    claim_next_assignment,
    mark_completed,
    mark_needs_attention,
)
from services.sponsor_research import (
    NoCredibleProspectsError,
    SponsorResearchError,
    SponsorResearchUnavailableError,
    research_sponsorship_asset,
)
from services.sponsor_research_diagnostics import (
    safely_persist_sponsor_research_diagnostics,
)

logger = logging.getLogger(__name__)


def process_next_sponsor_research_assignment(
    *, worker_id, lease_seconds=600, max_attempts=3,
    claim=claim_next_assignment, research=research_sponsorship_asset,
):
    assignment = claim(
        worker_id,
        lease_seconds=lease_seconds,
        max_attempts=max_attempts,
    )
    if assignment is None:
        return False
    assignment_id = assignment.id
    diagnostic_snapshot = None

    def capture_diagnostics(snapshot):
        nonlocal diagnostic_snapshot
        diagnostic_snapshot = snapshot

    try:
        organization = db.session.get(Organization, assignment.organization_id)
        initiative = db.session.get(
            SponsorshipInitiative, assignment.initiative_id
        )
        asset = db.session.get(
            SponsorshipAsset, assignment.sponsorship_asset_id
        )
        intelligence = get_sponsorship_intelligence(organization, initiative)
        if not all((organization, initiative, asset, intelligence)):
            raise SponsorResearchError(
                "The approved sponsorship opportunity is no longer available."
            )
        prior_names = [
            item.company_name
            for item in SponsorProspect.query.filter_by(
                organization_id=organization.id,
                initiative_id=initiative.id,
                sponsorship_asset_id=asset.id,
                is_active=True,
            ).all()
        ]
        candidates = research(
            organization,
            initiative,
            asset,
            intelligence.sponsor_eligibility,
            prior_results=prior_names,
            diagnostics_sink=capture_diagnostics,
        )
        safely_persist_sponsor_research_diagnostics(
            assignment, diagnostic_snapshot
        )
        mark_completed(assignment, candidates)
        logger.info(
            "sponsor_research_assignment_completed worker_id=%s assignment_id=%s",
            worker_id, assignment_id,
        )
    except (
        NoCredibleProspectsError,
        SponsorResearchUnavailableError,
        SponsorResearchError,
    ) as exc:
        db.session.rollback()
        assignment = db.session.get(type(assignment), assignment_id)
        safely_persist_sponsor_research_diagnostics(
            assignment, diagnostic_snapshot
        )
        mark_needs_attention(assignment, str(exc) or SAFE_FAILURE_MESSAGE)
        logger.warning(
            "sponsor_research_assignment_failed worker_id=%s assignment_id=%s",
            worker_id, assignment_id,
        )
    except Exception:
        db.session.rollback()
        assignment = db.session.get(type(assignment), assignment_id)
        safely_persist_sponsor_research_diagnostics(
            assignment, diagnostic_snapshot
        )
        mark_needs_attention(
            assignment, "Unexpected research processing failure."
        )
        logger.exception(
            "sponsor_research_assignment_failed worker_id=%s assignment_id=%s",
            worker_id, assignment_id,
        )
    return True

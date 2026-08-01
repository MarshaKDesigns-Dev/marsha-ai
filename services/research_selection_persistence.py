"""Atomic, cumulative persistence for reviewed Sponsor Research results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import Opportunity, ResearchAssignmentSelection, SponsorProspect
from extensions import db
from services.sponsor_prospect_persistence import (
    normalized_company_key,
    persist_sponsor_prospects,
)
from services.sponsor_research import SponsorProspectCandidate


@dataclass(frozen=True)
class ResearchSelectionResult:
    added_count: int
    already_saved_count: int


class ResearchSelectionPersistenceError(RuntimeError):
    """Raised after an atomic selection save has been rolled back."""


def _new_opportunity(organization, initiative, asset, prospect):
    return Opportunity(
        organization_id=organization.id,
        initiative_id=initiative.id,
        sponsorship_asset_id=asset.id,
        sponsor_prospect_id=prospect.id,
        parent_prospect=prospect.company_name,
        recommended_target=prospect.company_name,
        category=asset.name,
        score=prospect.ranking_score,
        contact_name=prospect.contact_name,
        title=prospect.contact_title,
        department=prospect.contact_department,
        email=prospect.contact_email,
        phone=prospect.contact_phone,
        contact_url=prospect.contact_url,
        why_this_contact=(
            "Public business contact information found during sponsor research."
            if prospect.contact_evidence_url
            else "No reliable public contact was found."
        ),
        confidence=prospect.confidence,
        verified_date=prospect.research_date.isoformat(),
        sources_json=prospect.evidence_json,
        stage="Research Approved",
    )


def save_research_selections(
    organization: Any,
    initiative: Any,
    assignment: Any,
    asset: Any,
    category: Any,
    candidates: list[SponsorProspectCandidate],
    *,
    session: Session | None = None,
) -> ResearchSelectionResult:
    """Add selected sponsors without replacing any established Pipeline data."""

    database_session = session or db.session
    added_count = 0
    already_saved_count = 0
    try:
        for candidate in candidates:
            company_key = normalized_company_key(
                candidate.company_name, candidate.website
            )
            prospect = database_session.scalar(
                select(SponsorProspect).where(
                    SponsorProspect.organization_id == organization.id,
                    SponsorProspect.initiative_id == initiative.id,
                    SponsorProspect.company_key == company_key,
                    SponsorProspect.is_active.is_(True),
                ).order_by(SponsorProspect.id.asc())
            )
            if prospect is None:
                prospect = persist_sponsor_prospects(
                    organization, initiative, category, [candidate],
                    session=database_session, sponsorship_asset=asset,
                    commit=False,
                )[0]
                database_session.flush()

            opportunity = database_session.scalar(
                select(Opportunity).where(
                    Opportunity.organization_id == organization.id,
                    Opportunity.initiative_id == initiative.id,
                    Opportunity.sponsor_prospect_id == prospect.id,
                ).order_by(Opportunity.id.asc())
            )
            if opportunity is None:
                opportunity = _new_opportunity(
                    organization, initiative, asset, prospect
                )
                database_session.add(opportunity)
                database_session.flush()
                added_count += 1
            else:
                already_saved_count += 1

            selection = database_session.scalar(
                select(ResearchAssignmentSelection).where(
                    ResearchAssignmentSelection.research_assignment_id
                    == assignment.id,
                    ResearchAssignmentSelection.sponsor_prospect_id
                    == prospect.id,
                )
            )
            if selection is None:
                database_session.add(ResearchAssignmentSelection(
                    research_assignment_id=assignment.id,
                    sponsor_prospect_id=prospect.id,
                    opportunity_id=opportunity.id,
                ))
        database_session.commit()
        return ResearchSelectionResult(added_count, already_saved_count)
    except Exception as exc:
        database_session.rollback()
        if isinstance(exc, ResearchSelectionPersistenceError):
            raise
        raise ResearchSelectionPersistenceError(
            "Research selections could not be saved."
        ) from exc

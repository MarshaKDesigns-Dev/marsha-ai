"""Atomic persistence for evidence-backed sponsor prospects."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import SponsorProspect
from extensions import db
from services.sponsor_research import SponsorProspectCandidate


class SponsorProspectPersistenceError(RuntimeError):
    """Raised when researched prospects cannot be saved atomically."""


def normalized_company_key(name: str, website: str) -> str:
    """Create a stable per-company deduplication key."""

    host = urlsplit(website).netloc.lower()
    host = host.removeprefix("www.")
    name_key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return host or name_key


def _serialize_evidence(candidate: SponsorProspectCandidate) -> str:
    return json.dumps(
        [
            evidence.model_dump(mode="json")
            for evidence in candidate.evidence_sources
        ],
        ensure_ascii=False,
        sort_keys=True,
    )


def _serialize_verified_information(
    candidate: SponsorProspectCandidate,
) -> str:
    return json.dumps(
        [
            fact.model_dump(mode="json")
            for fact in candidate.verified_information
        ],
        ensure_ascii=False,
        sort_keys=True,
    )


def persist_sponsor_prospects(
    organization: Any,
    initiative: Any,
    category: Any,
    candidates: list[SponsorProspectCandidate],
    *,
    session: Session | None = None,
    sponsorship_asset: Any | None = None,
    commit: bool = True,
) -> list[SponsorProspect]:
    """Upsert validated prospects in one transaction without deleting prior data."""

    if not candidates or not all(
        isinstance(item, SponsorProspectCandidate)
        for item in candidates
    ):
        raise SponsorProspectPersistenceError(
            "Validated sponsor prospects are required."
        )

    if (
        getattr(initiative, "organization_id", None)
        != getattr(organization, "id", None)
        or getattr(category, "organization_id", None) != organization.id
        or getattr(category, "initiative_id", None) != initiative.id
    ):
        raise SponsorProspectPersistenceError(
            "The category does not belong to the active initiative."
        )
    if sponsorship_asset is not None and (
        getattr(sponsorship_asset, "organization_id", None) != organization.id
        or getattr(sponsorship_asset, "initiative_id", None) != initiative.id
        or getattr(sponsorship_asset, "approval_status", None) != "Approved"
    ):
        raise SponsorProspectPersistenceError(
            "The sponsorship asset is not approved for the active initiative."
        )

    prepared = [
        (
            candidate,
            normalized_company_key(
                candidate.company_name,
                candidate.website,
            ),
            _serialize_evidence(candidate),
        )
        for candidate in candidates
    ]
    database_session = session or db.session

    try:
        saved = []
        for candidate, company_key, evidence_json in prepared:
            record = database_session.scalar(
                select(SponsorProspect).where(
                    SponsorProspect.initiative_id == initiative.id,
                    SponsorProspect.category_slug == category.slug,
                    SponsorProspect.company_key == company_key,
                )
            )
            if record is None:
                record = SponsorProspect(
                    organization_id=organization.id,
                    initiative_id=initiative.id,
                    category_slug=category.slug,
                    company_key=company_key,
                )
                database_session.add(record)

            record.sponsorship_asset_id = (
                sponsorship_asset.id if sponsorship_asset is not None else None
            )
            contact = candidate.contact
            record.company_name = candidate.company_name
            record.website = candidate.website
            record.location = candidate.location
            record.industry = candidate.industry
            record.why_fits = candidate.why_fits
            record.relevant_connection = candidate.relevant_connection
            record.geographic_relevance = candidate.geographic_relevance
            record.evidence_type = candidate.evidence_type.value
            record.evidence_json = evidence_json
            record.research_date = candidate.research_date
            record.confidence = candidate.confidence.value
            record.uncertainty_json = json.dumps(
                candidate.uncertainty,
                ensure_ascii=False,
            )
            record.ranking_score = candidate.ranking_score
            record.ranking_explanation = candidate.ranking_explanation
            record.verified_information_json = (
                _serialize_verified_information(candidate)
            )
            record.why_recommended = candidate.why_recommended
            record.organization_fit = candidate.organization_fit
            record.recommended_ask = candidate.recommended_ask
            record.contribution_type = candidate.contribution_type.value
            record.why_may_say_yes = candidate.why_may_say_yes
            record.why_may_say_yes_evidence_json = json.dumps(
                candidate.why_may_say_yes_evidence_urls,
                ensure_ascii=False,
                sort_keys=True,
            )
            record.recommendation_strength = (
                candidate.recommendation_strength.value
            )
            record.recommendation_strength_score = (
                candidate.recommendation_strength_score
            )
            record.strength_factors_json = json.dumps(
                candidate.strength_factors,
                ensure_ascii=False,
                sort_keys=True,
            )
            record.contact_name = contact.name if contact else None
            record.contact_title = contact.title if contact else None
            record.contact_department = contact.department if contact else None
            record.contact_email = contact.email if contact else None
            record.contact_phone = contact.phone if contact else None
            record.contact_url = contact.contact_url if contact else None
            record.contact_evidence_url = (
                contact.evidence_url if contact else None
            )
            record.is_active = True
            saved.append(record)

        if commit:
            database_session.commit()
        else:
            database_session.flush()
        return saved
    except SponsorProspectPersistenceError:
        database_session.rollback()
        raise
    except Exception as exc:
        database_session.rollback()
        raise SponsorProspectPersistenceError(
            "Sponsor prospects could not be saved."
        ) from exc

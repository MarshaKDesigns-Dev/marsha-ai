"""Persist validated sponsorship intelligence results.

This service accepts one completed SponsorshipIntelligenceResult and stores its
contents for an existing organization and sponsorship initiative.

The service does not call OpenAI, render templates, or depend on a Flask route.
All database changes are committed as one transaction.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import (
    ResearchPriority,
    SponsorCategory,
    SponsorshipAsset,
    SponsorshipIntelligence,
    db,
)
from services.sponsorship_intelligence import (
    SponsorshipIntelligenceResult,
)


class SponsorshipIntelligencePersistenceError(RuntimeError):
    """Raised when sponsorship intelligence cannot be persisted."""


def _json_dump(value: Any) -> str:
    """Serialize validated Pydantic data using stable JSON output."""

    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def _require_persisted_models(
    organization: Any,
    initiative: Any,
) -> None:
    """Validate that the organization and initiative can own saved results."""

    organization_id = getattr(organization, "id", None)
    initiative_id = getattr(initiative, "id", None)

    if organization_id is None:
        raise SponsorshipIntelligencePersistenceError(
            "The organization must be saved before intelligence is persisted."
        )

    if initiative_id is None:
        raise SponsorshipIntelligencePersistenceError(
            "The sponsorship initiative must be saved before intelligence "
            "is persisted."
        )

    initiative_organization_id = getattr(
        initiative,
        "organization_id",
        None,
    )

    if initiative_organization_id != organization_id:
        raise SponsorshipIntelligencePersistenceError(
            "The sponsorship initiative does not belong to the organization."
        )


def _get_or_create_intelligence_record(
    session: Session,
    organization: Any,
    initiative: Any,
) -> SponsorshipIntelligence:
    """Return the initiative intelligence record, creating it when absent."""

    record = session.scalar(
        select(SponsorshipIntelligence).where(
            SponsorshipIntelligence.initiative_id == initiative.id
        )
    )

    if record is None:
        record = SponsorshipIntelligence(
            organization_id=organization.id,
            initiative_id=initiative.id,
        )
        session.add(record)

    return record


def _replace_categories(
    session: Session,
    organization: Any,
    initiative: Any,
    result: SponsorshipIntelligenceResult,
) -> None:
    """Replace the initiative's sponsor categories."""

    session.execute(
        delete(SponsorCategory).where(
            SponsorCategory.initiative_id == initiative.id
        )
    )

    for category in result.sponsor_categories.categories:
        session.add(
            SponsorCategory(
                organization_id=organization.id,
                initiative_id=initiative.id,
                slug=category.slug,
                category=category.category,
                fit=category.fit,
                score=category.score,
                priority=category.priority,
                ideal_sponsor_profile=category.ideal_sponsor_profile,
                research_direction=category.research_direction,
                is_active=True,
            )
        )


def _replace_assets(
    session: Session,
    organization: Any,
    initiative: Any,
    result: SponsorshipIntelligenceResult,
) -> None:
    """Replace the initiative's sponsorship assets."""

    session.execute(
        delete(SponsorshipAsset).where(
            SponsorshipAsset.initiative_id == initiative.id
        )
    )

    for asset in result.sponsorship_assets.assets:
        session.add(
            SponsorshipAsset(
                organization_id=organization.id,
                initiative_id=initiative.id,
                name=asset.name,
                value=asset.sponsor_value,
                capacity=asset.capacity,
                description=asset.description,
                sponsor_value=asset.sponsor_value,
                audience_value=asset.audience_value,
                delivery_method=asset.delivery_method,
                exclusivity=asset.exclusivity,
                measurement_method=asset.measurement_method,
                recommended_categories_json=_json_dump(
                    asset.recommended_for_categories
                ),
                is_active=True,
            )
        )


def _replace_research_priorities(
    session: Session,
    organization: Any,
    initiative: Any,
    result: SponsorshipIntelligenceResult,
) -> None:
    """Replace the initiative's AI-generated research priorities."""

    session.execute(
        delete(ResearchPriority).where(
            ResearchPriority.initiative_id == initiative.id
        )
    )

    for priority in result.research_priorities.priorities:
        session.add(
            ResearchPriority(
                organization_id=organization.id,
                initiative_id=initiative.id,
                category_slug=priority.category_slug,
                priority=priority.priority,
                ideal_sponsor_profile=priority.ideal_sponsor_profile,
                research_direction=priority.research_direction,
                qualification_signals_json=_json_dump(
                    priority.qualification_signals
                ),
                verification_requirements_json=_json_dump(
                    priority.verification_requirements
                ),
                disqualification_signals_json=_json_dump(
                    priority.disqualification_signals
                ),
                recommended_asset_names_json=_json_dump(
                    priority.recommended_asset_names
                ),
                outreach_angle=priority.outreach_angle,
                is_active=True,
            )
        )


def persist_sponsorship_intelligence(
    organization: Any,
    initiative: Any,
    result: SponsorshipIntelligenceResult,
    *,
    session: Session | None = None,
) -> SponsorshipIntelligence:
    """Persist one complete sponsorship intelligence result.

    Existing generated categories, assets, and research priorities for the
    initiative are replaced. The high-level analysis and strategy record is
    created or updated.

    All changes are committed together. If any operation fails, the transaction
    is rolled back.

    Args:
        organization:
            A persisted Organization model instance.

        initiative:
            A persisted SponsorshipInitiative model instance belonging to the
            supplied organization.

        result:
            A validated SponsorshipIntelligenceResult from the orchestrator.

        session:
            Optional SQLAlchemy session used primarily for isolated tests.

    Returns:
        The created or updated SponsorshipIntelligence database record.

    Raises:
        SponsorshipIntelligencePersistenceError:
            If ownership validation fails or the transaction cannot complete.
    """

    _require_persisted_models(
        organization,
        initiative,
    )

    if not isinstance(result, SponsorshipIntelligenceResult):
        raise SponsorshipIntelligencePersistenceError(
            "A validated SponsorshipIntelligenceResult is required."
        )

    database_session = session or db.session

    try:
        intelligence_record = _get_or_create_intelligence_record(
            database_session,
            organization,
            initiative,
        )

        intelligence_record.organization_id = organization.id
        intelligence_record.initiative_id = initiative.id
        intelligence_record.organization_analysis_json = _json_dump(
            result.organization_analysis
        )
        intelligence_record.sponsorship_strategy_json = _json_dump(
            result.sponsorship_strategy
        )

        _replace_categories(
            database_session,
            organization,
            initiative,
            result,
        )

        _replace_assets(
            database_session,
            organization,
            initiative,
            result,
        )

        _replace_research_priorities(
            database_session,
            organization,
            initiative,
            result,
        )

        database_session.commit()

        return intelligence_record

    except SponsorshipIntelligencePersistenceError:
        database_session.rollback()
        raise

    except Exception as exc:
        database_session.rollback()

        raise SponsorshipIntelligencePersistenceError(
            "The sponsorship intelligence transaction could not be completed."
        ) from exc
        
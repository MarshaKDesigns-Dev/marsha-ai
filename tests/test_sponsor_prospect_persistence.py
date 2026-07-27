"""Tests for atomic sponsor prospect persistence."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import ResearchRecord, SponsorProspect
from services.sponsor_prospect_persistence import (
    SponsorProspectPersistenceError,
    persist_sponsor_prospects,
)
from services.sponsor_research import (
    ConfidenceLevel,
    ContributionType,
    EvidenceType,
    ProspectEvidence,
    SponsorProspectCandidate,
    VerifiedFact,
)


def candidate(contact=None):
    return SponsorProspectCandidate(
        company_name="Example Technology",
        website="https://example.com",
        location="Durham, NC",
        industry="Technology",
        why_fits="Its services align with the initiative.",
        relevant_connection="The company has a documented local program.",
        verified_information=[
            VerifiedFact(
                statement="The company documents a local program.",
                source_url="https://example.com/community",
            )
        ],
        why_recommended="Documented community activity supports consideration.",
        organization_fit="The local program aligns with the mission.",
        recommended_ask="Provide technology services for the event.",
        contribution_type=ContributionType.SERVICE,
        recommended_need="Marketing",
        why_may_say_yes="The request aligns with its documented local program.",
        why_may_say_yes_evidence_urls=[
            "https://example.com/community",
        ],
        geographic_relevance="It operates in Durham.",
        evidence_type=EvidenceType.COMMUNITY_INVOLVEMENT,
        evidence_sources=[
            ProspectEvidence(
                url="https://example.com/community",
                title="Community program",
                description="Official information about a local program.",
            )
        ],
        research_date=date(2026, 7, 24),
        confidence=ConfidenceLevel.HIGH,
        mission_fit_score=18,
        audience_fit_score=17,
        geographic_fit_score=18,
        evidence_score=22,
        contactability_score=10,
        need_alignment_score=18,
        industry_alignment_score=13,
        ask_credibility_score=14,
        contact=contact,
    )


def owners():
    return (
        SimpleNamespace(id=1),
        SimpleNamespace(id=2, organization_id=1),
        SimpleNamespace(
            id=3,
            organization_id=1,
            initiative_id=2,
            slug="technology",
        ),
    )


def test_persistence_saves_evidence_and_missing_contact():
    organization, initiative, category = owners()
    session = MagicMock()
    session.scalar.return_value = None

    records = persist_sponsor_prospects(
        organization,
        initiative,
        category,
        [candidate(contact=None)],
        session=session,
    )

    assert len(records) == 1
    record = records[0]
    assert isinstance(record, SponsorProspect)
    assert record.company_name == "Example Technology"
    assert "https://example.com/community" in record.evidence_json
    assert record.why_may_say_yes_evidence == [
        "https://example.com/community"
    ]
    assert record.contact_name is None
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_existing_company_is_updated_without_duplicate_insert():
    organization, initiative, category = owners()
    existing = SponsorProspect(
        organization_id=1,
        initiative_id=2,
        category_slug="technology",
        company_key="example.com",
    )
    session = MagicMock()
    session.scalar.return_value = existing

    records = persist_sponsor_prospects(
        organization,
        initiative,
        category,
        [candidate()],
        session=session,
    )

    assert records == [existing]
    session.add.assert_not_called()
    session.commit.assert_called_once()


def test_asset_scoped_persistence_preserves_selected_asset():
    organization, initiative, category = owners()
    asset = SimpleNamespace(
        id=9,
        organization_id=1,
        initiative_id=2,
        approval_status="Approved",
    )
    session = MagicMock()
    session.scalar.return_value = None

    records = persist_sponsor_prospects(
        organization,
        initiative,
        category,
        [candidate()],
        session=session,
        sponsorship_asset=asset,
    )

    assert records[0].sponsorship_asset_id == 9


def test_failed_research_persistence_rolls_back_existing_records():
    organization, initiative, category = owners()
    session = MagicMock()
    session.scalar.return_value = None
    session.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(SponsorProspectPersistenceError):
        persist_sponsor_prospects(
            organization,
            initiative,
            category,
            [candidate()],
            session=session,
        )

    session.rollback.assert_called_once()


def test_invalid_ownership_does_not_write():
    organization, initiative, category = owners()
    category.organization_id = 99
    session = MagicMock()

    with pytest.raises(SponsorProspectPersistenceError):
        persist_sponsor_prospects(
            organization,
            initiative,
            category,
            [candidate()],
            session=session,
        )

    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_legacy_contact_research_records_remain_readable():
    record = ResearchRecord(
        prospect_key="healthcare:0",
        parent_prospect="Legacy Prospect",
        sources_json=(
            '[{"label": "Official source", '
            '"url": "https://legacy.example"}]'
        ),
    )

    assert record.sources == [
        {
            "label": "Official source",
            "url": "https://legacy.example",
        }
    ]

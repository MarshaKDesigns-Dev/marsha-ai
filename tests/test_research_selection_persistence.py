"""Regression tests for cumulative Sponsor Research selections."""

from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import Opportunity, ResearchAssignmentSelection, SponsorProspect, db
from services.research_selection_persistence import save_research_selections
from services.sponsor_prospect_persistence import normalized_company_key
from tests.test_sponsor_prospect_persistence import candidate


def _session():
    engine = create_engine("sqlite://")
    db.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _owners(asset_id=3, assignment_id=4):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=2, organization_id=1)
    asset = SimpleNamespace(
        id=asset_id,
        name="Recognition Partner",
        organization_id=1,
        initiative_id=2,
        approval_status="Approved",
    )
    assignment = SimpleNamespace(id=assignment_id)
    category = SimpleNamespace(
        organization_id=1, initiative_id=2, slug=f"asset-{asset_id}"
    )
    return organization, initiative, assignment, asset, category


def test_selections_accumulate_and_repeat_save_is_idempotent():
    session = _session()
    owners = _owners()
    first = candidate()
    second = candidate().model_copy(update={
        "company_name": "Second Sponsor",
        "website": "https://second.example",
    })

    result_one = save_research_selections(
        *owners, [first], session=session
    )
    opportunity = session.scalar(select(Opportunity))
    opportunity.stage = "Ready to Send"
    opportunity.contact_name = "Preserved Contact"
    session.commit()
    result_two = save_research_selections(
        *owners, [first, second], session=session
    )

    assert result_one.added_count == 1
    assert result_two.added_count == 1
    assert result_two.already_saved_count == 1
    assert session.query(SponsorProspect).count() == 2
    assert session.query(Opportunity).count() == 2
    assert session.query(ResearchAssignmentSelection).count() == 2
    preserved = session.get(Opportunity, opportunity.id)
    assert preserved.stage == "Ready to Send"
    assert preserved.contact_name == "Preserved Contact"

    repeated = save_research_selections(
        *owners, [first], session=session
    )
    assert repeated == type(repeated)(added_count=0, already_saved_count=1)
    assert session.query(Opportunity).count() == 2
    assert session.query(ResearchAssignmentSelection).count() == 2


def test_same_domain_across_assets_reuses_initiative_pipeline_record():
    session = _session()
    first_owners = _owners(asset_id=3, assignment_id=4)
    second_owners = _owners(asset_id=8, assignment_id=9)

    save_research_selections(*first_owners, [candidate()], session=session)
    result = save_research_selections(
        *second_owners, [candidate()], session=session
    )

    assert result.added_count == 0
    assert result.already_saved_count == 1
    assert session.query(SponsorProspect).count() == 1
    assert session.query(Opportunity).count() == 1
    assert session.query(ResearchAssignmentSelection).count() == 2


def test_company_identity_prefers_domain_and_has_normalized_name_fallback():
    assert normalized_company_key("Example LLC", "https://www.example.com/a") == (
        normalized_company_key("Example Incorporated", "https://example.com/b")
    )
    assert normalized_company_key("Example LLC", "") == "example-llc"
    assert normalized_company_key("Example LLC", "https://one.example") != (
        normalized_company_key("Example LLC", "https://two.example")
    )

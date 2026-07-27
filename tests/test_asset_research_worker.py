"""Focused coverage for asset-scoped Research Worker behavior."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app as app_module
from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_research import (
    NoCredibleProspectsError,
    SponsorResearchResult,
    research_sponsorship_asset,
)


def eligibility():
    return SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support community leadership.",
            location="Durham, NC",
            initiative_name="Leadership Summit",
            audience="Adults 21 and older",
        )
    )


def test_asset_research_prompt_contains_only_selected_asset():
    response = SimpleNamespace(
        output_parsed=SponsorResearchResult(prospects=[]),
        output=[],
    )
    client = MagicMock()
    client.with_options.return_value.responses.parse.return_value = response
    selected = SimpleNamespace(
        id=7,
        name="Official Venue Partner",
        description="Event venue with meeting space.",
        capacity="1 venue",
        sponsor_value="Naming and attendee visibility.",
    )

    with pytest.raises(NoCredibleProspectsError):
        research_sponsorship_asset(
            SimpleNamespace(
                name="Bright Futures",
                organization_type="Foundation",
                mission="Support youth leadership.",
                location="Durham, NC",
            ),
            SimpleNamespace(
                name="Leadership Summit",
                audience="Adults 21 and older",
                needs="Venue",
                goals="Deliver the summit",
                desired_sponsor_categories_json='["Hospitality"]',
            ),
            selected,
            eligibility(),
            prior_results=["Previously Researched Venue"],
            client=client,
        )

    prompt = (
        client.with_options.return_value.responses.parse.call_args.kwargs[
            "input"
        ]
    )
    assert "Official Venue Partner" in prompt
    assert "Event venue with meeting space." in prompt
    assert "1 venue" in prompt
    assert "Previously Researched Venue" in prompt
    assert "Research only the selected sponsorship asset" in prompt
    assert "Return 5-10 real companies" in prompt


def test_research_landing_queries_only_approved_scoped_assets(monkeypatch):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    asset = SimpleNamespace(
        id=33,
        name="Custom Photography Partner",
        description="Approved custom asset",
        sponsor_value="Brand visibility",
        value=None,
    )
    asset_query = MagicMock()
    asset_query.filter_by.return_value.order_by.return_value.all.return_value = [
        asset
    ]
    assignment_query = MagicMock()
    assignment_query.filter_by.return_value.order_by.return_value.all.return_value = (
        []
    )
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: organization,
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: initiative,
    )
    monkeypatch.setattr(
        app_module,
        "SponsorshipAsset",
        SimpleNamespace(
            query=asset_query,
            created_at=SimpleNamespace(asc=lambda: "created"),
        ),
    )
    monkeypatch.setattr(
        app_module,
        "ResearchAssignment",
        SimpleNamespace(
            query=assignment_query,
            created_at=SimpleNamespace(desc=lambda: "created"),
        ),
    )
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(query=opportunity_query),
    )

    response = app_module.app.test_client().get("/research")

    assert response.status_code == 200
    assert b"Custom Photography Partner" in response.data
    asset_query.filter_by.assert_called_once_with(
        organization_id=11,
        initiative_id=22,
        is_active=True,
        approval_status="Approved",
    )


def test_research_worker_with_no_approved_assets_renders_empty_state(monkeypatch):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    asset_query = MagicMock()
    asset_query.filter_by.return_value.order_by.return_value.all.return_value = []
    assignment_query = MagicMock()
    assignment_query.filter_by.return_value.order_by.return_value.all.return_value = []
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(
        app_module,
        "SponsorshipAsset",
        SimpleNamespace(
            query=asset_query,
            created_at=SimpleNamespace(asc=lambda: "created"),
        ),
    )
    monkeypatch.setattr(
        app_module,
        "ResearchAssignment",
        SimpleNamespace(
            query=assignment_query,
            created_at=SimpleNamespace(desc=lambda: "created"),
        ),
    )
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(query=opportunity_query),
    )

    response = app_module.app.test_client().get("/research")

    assert response.status_code == 200
    assert b"No approved sponsorship assets are ready." in response.data
    assert b"Review sponsorship assets" in response.data
    assert b"/workspace/assets" in response.data


def test_invalid_active_category_scope_returns_none(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_active_organization",
        lambda: SimpleNamespace(id=11),
    )
    monkeypatch.setattr(
        app_module,
        "get_active_initiative",
        lambda: SimpleNamespace(id=22, organization_id=99),
    )

    assert app_module.get_active_sponsor_category("financial-services") is None


def test_persisted_failure_details_render_on_results_page(monkeypatch):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    assignment = SimpleNamespace(
        id=44,
        organization_id=11,
        initiative_id=22,
        sponsorship_asset_id=33,
        status="needs_attention",
        error_details="Public evidence could not be verified.",
        results=[],
    )
    assignment_query = MagicMock()
    assignment_query.filter_by.return_value.first_or_404.return_value = assignment
    asset = SimpleNamespace(id=33, name="Venue Partner")
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(
        app_module,
        "ResearchAssignment",
        SimpleNamespace(query=assignment_query),
    )
    monkeypatch.setattr(
        app_module,
        "_approved_research_asset",
        lambda *args: asset,
    )

    response = app_module.app.test_client().get("/research/assignments/44")

    assert response.status_code == 200
    assert b"What happened:" in response.data
    assert b"Public evidence could not be verified." in response.data


def test_failed_asset_research_leaves_no_partial_prospects_or_opportunities(
    monkeypatch,
):
    import services.sponsor_research as research_service

    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    asset = SimpleNamespace(id=33, name="Venue Partner")
    assignment = SimpleNamespace(
        id=44,
        status="working",
        started_at=None,
        completed_at=None,
        result_count=0,
        results_json="[]",
        error_details=None,
    )
    assignment_query = MagicMock()
    assignment_query.filter_by.return_value.first.return_value = None
    assignment_model = MagicMock(return_value=assignment)
    assignment_model.query = assignment_query
    prospect_query = MagicMock()
    prospect_query.filter_by.return_value.all.return_value = []
    opportunity_model = MagicMock()
    add = MagicMock()
    commit = MagicMock()
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(
        app_module, "_approved_research_asset", lambda *args: asset
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda *args: SimpleNamespace(sponsor_eligibility=eligibility()),
    )
    monkeypatch.setattr(app_module, "ResearchAssignment", assignment_model)
    monkeypatch.setattr(
        app_module,
        "SponsorProspect",
        SimpleNamespace(query=prospect_query),
    )
    monkeypatch.setattr(app_module, "Opportunity", opportunity_model)
    monkeypatch.setattr(app_module.db.session, "add", add)
    monkeypatch.setattr(app_module.db.session, "commit", commit)
    monkeypatch.setattr(
        research_service,
        "research_sponsorship_asset",
        MagicMock(
            side_effect=NoCredibleProspectsError(
                "Public evidence could not be verified.",
                reason_code="web_evidence_not_returned",
            )
        ),
    )

    response = app_module.app.test_client().post("/research/assets/33")

    assert response.status_code == 302
    assert response.location.endswith("/research/assignments/44")
    assert assignment.status == "needs_attention"
    assert assignment.result_count == 0
    assert assignment.results_json == "[]"
    assert assignment.error_details == "Public evidence could not be verified."
    add.assert_called_once_with(assignment)
    opportunity_model.assert_not_called()
    commit.assert_called()


def test_duplicate_result_selection_creates_one_asset_scoped_opportunity(
    monkeypatch,
):
    import services.sponsor_prospect_persistence as persistence_service
    import services.sponsor_research as research_service

    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    asset = SimpleNamespace(id=33, name="Venue Partner")
    assignment = SimpleNamespace(
        id=44,
        sponsorship_asset_id=33,
        results=[{"company_name": "Venue Co"}],
    )
    assignment_query = MagicMock()
    assignment_query.filter_by.return_value.first_or_404.return_value = assignment
    assignment_model = SimpleNamespace(query=assignment_query)
    prospect = SimpleNamespace(
        id=55,
        company_name="Venue Co",
        ranking_score=82,
        confidence="high",
        research_date=SimpleNamespace(isoformat=lambda: "2026-07-27"),
        evidence_json="[]",
    )
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.first.return_value = None
    opportunity_model = MagicMock()
    opportunity_model.query = opportunity_query
    created_opportunity = SimpleNamespace()
    opportunity_model.return_value = created_opportunity
    add = MagicMock()
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(app_module, "ResearchAssignment", assignment_model)
    monkeypatch.setattr(
        app_module, "_approved_research_asset", lambda *args: asset
    )
    monkeypatch.setattr(app_module, "Opportunity", opportunity_model)
    monkeypatch.setattr(app_module.db.session, "add", add)
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())
    monkeypatch.setattr(
        research_service.SponsorProspectCandidate,
        "model_validate",
        MagicMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        persistence_service,
        "persist_sponsor_prospects",
        MagicMock(return_value=[prospect]),
    )

    response = app_module.app.test_client().post(
        "/research/assignments/44/review",
        data={"selected_results": ["0", "0"]},
    )

    assert response.status_code == 302
    opportunity_model.assert_called_once_with(
        organization_id=11,
        initiative_id=22,
        sponsorship_asset_id=33,
        sponsor_prospect_id=55,
        parent_prospect="Venue Co",
        recommended_target="Venue Co",
        category="Venue Partner",
        score=82,
        confidence="high",
        verified_date="2026-07-27",
        sources_json="[]",
        stage="Research Approved",
    )
    add.assert_called_once_with(created_opportunity)


def test_pipeline_queries_only_active_asset_scoped_opportunities(monkeypatch):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    opportunity_query = MagicMock()
    opportunity_query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module, "get_active_organization", lambda: organization
    )
    monkeypatch.setattr(
        app_module, "get_active_initiative", lambda: initiative
    )
    monkeypatch.setattr(
        app_module,
        "Opportunity",
        SimpleNamespace(
            query=opportunity_query,
            updated_at=SimpleNamespace(desc=lambda: "updated"),
        ),
    )

    response = app_module.app.test_client().get("/pipeline")

    assert response.status_code == 200
    opportunity_query.filter_by.assert_called_once_with(
        organization_id=11,
        initiative_id=22,
    )


def test_research_templates_require_explicit_review_controls():
    landing = app_module.app.jinja_loader.get_source(
        app_module.app.jinja_env,
        "research_worker.html",
    )[0]
    results = app_module.app.jinja_loader.get_source(
        app_module.app.jinja_env,
        "research_results.html",
    )[0]

    assert "Which" in landing
    assert "sponsorship opportunity would you like me to research first?" in landing
    assert "Research Worker is working" in landing
    assert "button.disabled = true" in landing
    assert "Save Selected to Pipeline" in results
    assert "Save All to Pipeline" in results
    assert "Reject All" in results
    assert "Research more for this asset" in results
    assert "Choose another asset" in results
    assert "assignment.error_details" in results


def test_assignment_and_pipeline_models_preserve_asset_scope():
    assignment_columns = app_module.ResearchAssignment.__table__.columns
    prospect_columns = app_module.SponsorProspect.__table__.columns
    opportunity_columns = app_module.Opportunity.__table__.columns

    assert "organization_id" in assignment_columns
    assert "initiative_id" in assignment_columns
    assert "sponsorship_asset_id" in assignment_columns
    assert "result_count" in assignment_columns
    assert "error_details" in assignment_columns
    assert "sponsorship_asset_id" in prospect_columns
    assert "sponsorship_asset_id" in opportunity_columns
    assert "sponsor_prospect_id" in opportunity_columns
    assert app_module.ResearchAssignment.__table__.c.organization_id.nullable is False
    assert app_module.ResearchAssignment.__table__.c.initiative_id.nullable is False
    assert (
        app_module.ResearchAssignment.__table__.c.sponsorship_asset_id.nullable
        is False
    )
    assert "ix_research_assignment_scope" in {
        index.name for index in app_module.ResearchAssignment.__table__.indexes
    }

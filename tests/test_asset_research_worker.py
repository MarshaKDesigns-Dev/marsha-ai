"""Focused coverage for asset-scoped Research Worker behavior."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import render_template

import app as app_module
from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_research import (
    NoCredibleProspectsError,
    SponsorResearchError,
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
        id="resp_asset_test",
        status="completed",
        incomplete_details=None,
        usage=None,
        output=[
            {
                "type": "message",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": SponsorResearchResult(
                            prospects=[]
                        ).model_dump_json(),
                    }
                ],
            }
        ],
    )
    client = MagicMock()
    raw_response = MagicMock()
    raw_response.parse.return_value = response
    raw_response.status_code = 200
    client.with_options.return_value.responses.with_raw_response.create.return_value = (
        raw_response
    )
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
        client.with_options.return_value.responses.with_raw_response.create.call_args.kwargs[
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
    initiative = SimpleNamespace(
        id=22,
        organization_id=11,
        sponsorship_needs_json='["Photography", "Venue", "Other"]',
        sponsorship_needs_other="Transportation for speakers",
    )
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
    assert b"Setup needs included:</strong>\n        Photography" in response.data
    assert b"Needs without an approved Sponsor Opportunity:" in response.data
    assert b"Venue" in response.data
    assert b"Additional setup needs to verify:" in response.data
    assert b"Transportation for speakers" in response.data
    assert b"Add and approve a custom asset" in response.data
    asset_query.filter_by.assert_called_once_with(
        organization_id=11,
        initiative_id=22,
        is_active=True,
        approval_status="Approved",
    )


def test_research_worker_with_no_approved_assets_renders_empty_state(monkeypatch):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(
        id=22,
        organization_id=11,
        sponsorship_needs_json='["Venue"]',
        sponsorship_needs_other="",
    )
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
    assert b"Your Research Worker needs your attention." in response.data
    assert b"saved sponsors, and pipeline records were preserved" in response.data
    assert b"What happened:" not in response.data
    assert b"Public evidence could not be verified." not in response.data


def test_asset_research_route_enqueues_without_running_ai(
    monkeypatch,
):
    import services.research_assignments as assignment_service
    import services.sponsor_research as research_service

    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    asset = SimpleNamespace(id=33, name="Venue Partner")
    assignment = SimpleNamespace(
        id=44,
        status="ready",
        started_at=None,
        completed_at=None,
        result_count=0,
        results_json="[]",
        error_details=None,
    )
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
    enqueue = MagicMock(return_value=(assignment, True))
    monkeypatch.setattr(assignment_service, "enqueue_assignment", enqueue)
    research = MagicMock()
    monkeypatch.setattr(
        research_service,
        "research_sponsorship_asset",
        research,
    )

    response = app_module.app.test_client().post("/research/assets/33")

    assert response.status_code == 302
    assert response.location.endswith("/research/assignments/44")
    assert assignment.status == "ready"
    assert assignment.result_count == 0
    assert assignment.results_json == "[]"
    assert assignment.error_details is None
    enqueue.assert_called_once_with(organization, initiative, asset)
    research.assert_not_called()


def test_asset_research_route_does_not_enqueue_blocked_eligibility(
    monkeypatch,
):
    import services.research_assignments as assignment_service

    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    asset = SimpleNamespace(id=33, name="Scholarship Partner")
    blocked = SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support community leadership.",
            location="Durham, NC",
            initiative_name="Leadership Summit",
            audience="Entrepreneurs, executives, and students.",
        )
    )
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
        lambda *args: SimpleNamespace(sponsor_eligibility=blocked),
    )
    enqueue = MagicMock()
    monkeypatch.setattr(assignment_service, "enqueue_assignment", enqueue)

    response = app_module.app.test_client().post("/research/assets/33")

    assert response.status_code == 302
    assert response.location.endswith("/research")
    enqueue.assert_not_called()


def test_blocked_asset_research_does_not_call_provider():
    client = MagicMock()
    blocked = SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support community leadership.",
            location="Durham, NC",
            initiative_name="Leadership Summit",
            audience="Women entrepreneurs, executives, and students.",
        )
    )

    with pytest.raises(
        SponsorResearchError,
        match="audience age context is confirmed",
    ):
        research_sponsorship_asset(
            SimpleNamespace(name="Alliance", mission="Leadership"),
            SimpleNamespace(name="Summit", audience="Students"),
            SimpleNamespace(
                name="Named Participant Scholarship",
                description="Fund participant scholarships.",
                sponsor_value="Named recognition.",
            ),
            blocked,
            client=client,
        )

    client.with_options.assert_not_called()


def test_duplicate_result_selection_creates_one_asset_scoped_opportunity(
    monkeypatch,
):
    import services.research_selection_persistence as selection_service
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
        contact_name="Jordan Lee",
        contact_title="Partnerships Director",
        contact_department="Community Partnerships",
        contact_email="jordan@example.com",
        contact_phone="919-555-0100",
        contact_url="https://example.com/contact",
        contact_evidence_url="https://example.com/contact",
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
    save = MagicMock(
        return_value=selection_service.ResearchSelectionResult(1, 0)
    )
    monkeypatch.setattr(selection_service, "save_research_selections", save)

    response = app_module.app.test_client().post(
        "/research/assignments/44/review",
        data={"selected_results": ["0", "0"]},
    )

    assert response.status_code == 302
    assert response.location.endswith("/pipeline?new_sponsors=1")
    save.assert_called_once()


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
    assert "Sponsor Opportunity would you like me to research first?" in landing
    assert "worker_status_copy('research').working_title" in landing
    assert "button.disabled = true" in landing
    assert "Setup needs included:" in landing
    assert "Add and approve a custom asset" in landing
    assert "Previous research assignments ({{ assignment_history|length }})" in landing
    assert "Save Selected to Sponsor Pipeline" in results
    assert "Save All to Sponsor Pipeline" in results
    assert "Leave Results Unchanged" in results
    assert "Saved from this assignment" in results
    assert "Already in Sponsor Pipeline" in results
    assert "Open Opportunity" in results
    assert "Research More for This Asset" in results
    assert results.count("Choose another asset") == 1
    assert "assignment.error_details" not in results
    assert "worker_status_copy('research').failure_message" in results
    assert results.count("worker_status_copy('research').retry_action") == 1


def _research_result():
    return SimpleNamespace(
        company_name="Example Sponsor",
        confidence="high",
        why_fits="Strong fit",
        location="Durham, NC",
        recommended_ask="Scholarship Partner",
        evidence_sources=[],
    )


def test_research_results_switch_to_research_more_after_all_results_saved():
    assignment = SimpleNamespace(id=44, status="completed")
    asset = SimpleNamespace(id=33, name="Scholarship Partner")
    with app_module.app.test_request_context("/research/assignments/44"):
        rendered = render_template(
            "research_results.html",
            assignment=assignment,
            asset=asset,
            results=[_research_result()],
            saved_results={
                0: {
                    "status": "saved_from_assignment",
                    "opportunity_id": 9,
                }
            },
            has_selectable_results=False,
        )

    assert "Sponsor research is ready for review" not in rendered
    assert "Save Selected to Sponsor Pipeline" not in rendered
    assert "Save All to Sponsor Pipeline" not in rendered
    assert rendered.count("Research More for This Asset") == 1
    assert 'action="/research/assets/33"' in rendered
    assert 'method="post"' in rendered
    assert 'href="/opportunity/9"' in rendered


def test_research_results_keep_review_controls_for_selectable_results():
    assignment = SimpleNamespace(id=44, status="completed")
    asset = SimpleNamespace(id=33, name="Scholarship Partner")
    with app_module.app.test_request_context("/research/assignments/44"):
        rendered = render_template(
            "research_results.html",
            assignment=assignment,
            asset=asset,
            results=[_research_result()],
            saved_results={},
            has_selectable_results=True,
        )

    assert "Sponsor research is ready for review" in rendered
    assert "Save Selected to Sponsor Pipeline" in rendered
    assert "Save All to Sponsor Pipeline" in rendered
    assert "Research More for This Asset" not in rendered


def test_leave_results_unchanged_returns_to_research_selection(monkeypatch):
    organization = SimpleNamespace(id=11)
    initiative = SimpleNamespace(id=22, organization_id=11)
    assignment = SimpleNamespace(
        id=44, organization_id=11, initiative_id=22,
        sponsorship_asset_id=33, status="completed",
    )
    query = MagicMock()
    query.filter_by.return_value.first_or_404.return_value = assignment
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    monkeypatch.setattr(
        app_module, "ResearchAssignment", SimpleNamespace(query=query)
    )
    monkeypatch.setattr(
        app_module, "_approved_research_asset", lambda *args: SimpleNamespace(id=33)
    )

    response = app_module.app.test_client().post(
        "/research/assignments/44/review",
        data={"action": "reject_all"},
    )

    assert response.status_code == 302
    assert response.location.endswith("/research")


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

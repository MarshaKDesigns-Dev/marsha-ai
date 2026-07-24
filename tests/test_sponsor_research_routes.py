"""Route tests for evidence-backed sponsor research."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import app as app_module
from services.sponsor_eligibility import EligibilityFacts
from services.sponsor_eligibility_engine import SponsorEligibilityEngine
from services.sponsor_eligibility_gate import CategoryResearchDecision
from services.sponsor_research import NoCredibleProspectsError


def configure_route(monkeypatch):
    organization = SimpleNamespace(id=1)
    initiative = SimpleNamespace(id=2, organization_id=1)
    category = SimpleNamespace(
        id=3,
        organization_id=1,
        initiative_id=2,
        slug="technology",
        category="Technology",
        research_direction="Research local technology firms",
        ideal_sponsor_profile="Community-oriented technology firms",
    )
    eligibility = SponsorEligibilityEngine().evaluate(
        EligibilityFacts(
            mission="Support education.",
            location="Durham, NC",
            initiative_name="Education Conference",
            audience="Adults 21 and older",
        )
    )
    monkeypatch.setattr(
        app_module,
        "get_category_research_decision",
        lambda slug: CategoryResearchDecision(allowed=True),
    )
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
        "get_active_sponsor_category",
        lambda slug: category,
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_intelligence",
        lambda org, init: SimpleNamespace(
            sponsor_eligibility=eligibility,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "get_sponsorship_assets",
        lambda org, init: [],
    )
    query = MagicMock()
    query.filter_by.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(
        app_module,
        "SponsorProspect",
        SimpleNamespace(
            query=query,
            ranking_score=SimpleNamespace(desc=lambda: "ranking"),
            company_name=SimpleNamespace(asc=lambda: "company"),
        ),
    )


def test_no_credible_results_show_controlled_message(monkeypatch):
    configure_route(monkeypatch)
    persistence = MagicMock()

    def no_results(*args, **kwargs):
        raise NoCredibleProspectsError(
            "No credible sponsor prospects were found for this category."
        )

    monkeypatch.setattr(
        "services.sponsor_research.research_sponsor_category",
        no_results,
    )
    monkeypatch.setattr(
        "services.sponsor_prospect_persistence.persist_sponsor_prospects",
        persistence,
    )

    response = app_module.app.test_client().post("/prospects/technology")

    assert response.status_code == 200
    assert (
        b"No credible sponsor prospects were found for this category."
        in response.data
    )
    assert b"Duke Health" not in response.data
    persistence.assert_not_called()
    assert not hasattr(app_module, "PROSPECTS")


def test_research_failure_preserves_existing_results(monkeypatch):
    configure_route(monkeypatch)
    existing = SimpleNamespace(
        id=7,
        company_name="Verified Existing Company",
        website="https://existing.example",
        location="Durham, NC",
        industry="Technology",
        why_fits="Verified fit",
        relevant_connection="Verified local operation",
        geographic_relevance="Durham office",
        evidence_type="strategic_fit",
        ranking_score=70,
        ranking_explanation="Ranked 70/100.",
        research_date="2026-07-24",
        confidence="medium",
        uncertainty=[],
        evidence_sources=[
            {
                "url": "https://existing.example/about",
                "title": "About",
                "description": "Official company information",
            }
        ],
    )
    app_module.SponsorProspect.query.filter_by.return_value.order_by.return_value.all.return_value = [
        existing
    ]

    monkeypatch.setattr(
        "services.sponsor_research.research_sponsor_category",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            NoCredibleProspectsError(
                "No credible sponsor prospects were found for this category."
            )
        ),
    )

    response = app_module.app.test_client().post("/prospects/technology")

    assert response.status_code == 200
    assert b"Verified Existing Company" in response.data

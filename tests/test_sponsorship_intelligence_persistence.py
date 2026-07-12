"""Tests for sponsorship intelligence persistence."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import (
    ResearchPriority,
    SponsorCategory,
    SponsorshipAsset,
    SponsorshipIntelligence,
)
from services.organization_analysis import OrganizationAnalysis
from services.research_priorities import (
    ResearchPriorityRecommendation,
    ResearchPrioritySet,
)
from services.sponsor_categories import (
    SponsorCategoryRecommendation,
    SponsorCategorySet,
)
from services.sponsorship_assets import (
    SponsorshipAssetRecommendation,
    SponsorshipAssetSet,
)
from services.sponsorship_intelligence import (
    SponsorshipIntelligenceResult,
)
from services.sponsorship_intelligence_persistence import (
    SponsorshipIntelligencePersistenceError,
    persist_sponsorship_intelligence,
)
from services.sponsorship_strategy import (
    SponsorshipObjective,
    SponsorshipStrategy,
)


@pytest.fixture
def organization():
    return SimpleNamespace(
        id=10,
        name="Community Arts Center",
    )


@pytest.fixture
def initiative():
    return SimpleNamespace(
        id=20,
        organization_id=10,
        name="Summer Arts Festival",
    )


@pytest.fixture
def intelligence_result():
    analysis = OrganizationAnalysis(
        organization_summary=(
            "A community arts nonprofit delivering accessible education and "
            "creative programming for local residents."
        ),
        initiative_summary=(
            "A summer arts festival seeking sponsorship to expand affordable "
            "community programming and participation."
        ),
        mission_strengths=[
            "Accessible arts education",
        ],
        community_impact=[
            "Expanded access to creative programming",
        ],
        target_audiences=[
            "Families",
        ],
        sponsorship_objectives=[
            "Secure aligned financial and in-kind partners",
        ],
        sponsor_value_proposition=(
            "Sponsors can support community access while receiving credible "
            "visibility with local families and residents."
        ),
        strategy_direction=(
            "Prioritize community-oriented businesses with relevant customer "
            "audiences and measurable activation opportunities."
        ),
        risks_or_gaps=[
            "Verified attendance information is not yet available.",
        ],
    )

    strategy = SponsorshipStrategy(
        positioning_statement=(
            "Position the festival as an accessible community arts platform "
            "that connects aligned sponsors with local families."
        ),
        strategic_theme="Accessible arts and community participation",
        recommended_approach=(
            "Build partnerships around community access, useful audience "
            "experiences, credible visibility, and documented delivery."
        ),
        objectives=[
            SponsorshipObjective(
                objective="Secure aligned sponsorship support",
                rationale=(
                    "Aligned support can expand programming while preserving "
                    "the initiative's community-centered purpose."
                ),
                success_measure=(
                    "Document approved partners and the support committed."
                ),
            )
        ],
        sponsor_benefits=[
            "Relevant community visibility",
        ],
        partnership_principles=[
            "Use only credible and deliverable sponsor benefits",
        ],
        activation_priorities=[
            "Audience-facing arts engagement",
        ],
        measurement_priorities=[
            "Document delivered sponsor recognition",
        ],
        recommended_next_steps=[
            "Research the highest-priority sponsor categories",
        ],
        risks_or_constraints=[
            "Audience scale has not been verified.",
        ],
    )

    categories = SponsorCategorySet(
        categories=[
            SponsorCategoryRecommendation(
                slug="financial-services",
                category="Financial Services",
                fit=(
                    "Community-focused financial institutions may align with "
                    "accessible education and local family engagement."
                ),
                score=91,
                priority=1,
                ideal_sponsor_profile=(
                    "A regional financial institution with documented "
                    "community investment priorities."
                ),
                research_direction=(
                    "Research institutions supporting education, families, "
                    "financial wellness, or community development."
                ),
            ),
            SponsorCategoryRecommendation(
                slug="healthcare",
                category="Healthcare",
                fit=(
                    "Healthcare organizations may align with family access, "
                    "community wellbeing, and public engagement."
                ),
                score=87,
                priority=2,
                ideal_sponsor_profile=(
                    "A local healthcare provider with community education "
                    "or family engagement priorities."
                ),
                research_direction=(
                    "Research local providers with verified community benefit "
                    "or public education programs."
                ),
            ),
            SponsorCategoryRecommendation(
                slug="local-retail",
                category="Local Retail",
                fit=(
                    "Local retailers may value neighborhood visibility and "
                    "direct engagement with participating families."
                ),
                score=82,
                priority=3,
                ideal_sponsor_profile=(
                    "A locally active retailer serving families and supporting "
                    "community events."
                ),
                research_direction=(
                    "Research retailers with local decision-making authority "
                    "and documented event partnerships."
                ),
            ),
        ]
    )

    assets = SponsorshipAssetSet(
        assets=[
            SponsorshipAssetRecommendation(
                name="Community Arts Activity Partner",
                description=(
                    "The sponsor supports and receives recognition around a "
                    "specific audience-facing arts activity."
                ),
                sponsor_value=(
                    "The sponsor receives relevant visibility connected to a "
                    "useful and positive participant experience."
                ),
                audience_value=(
                    "Participants receive an additional accessible arts activity."
                ),
                delivery_method=(
                    "Deliver the activity onsite with agreed sponsor recognition."
                ),
                capacity="Limited",
                exclusivity="Non-exclusive",
                measurement_method=(
                    "Record delivery, placement, participation, and photographs."
                ),
                recommended_for_categories=[
                    "financial-services",
                    "healthcare",
                ],
            ),
            SponsorshipAssetRecommendation(
                name="Festival Welcome Partner",
                description=(
                    "The sponsor receives recognition within the festival "
                    "welcome experience and attendee information."
                ),
                sponsor_value=(
                    "The sponsor gains early event visibility in a prominent "
                    "but appropriately limited placement."
                ),
                audience_value=(
                    "Attendees receive clearer arrival and event information."
                ),
                delivery_method=(
                    "Include recognition in welcome signage and materials."
                ),
                capacity="1",
                exclusivity="Exclusive",
                measurement_method=(
                    "Retain final materials and photographs of placements."
                ),
                recommended_for_categories=[
                    "local-retail",
                ],
            ),
            SponsorshipAssetRecommendation(
                name="Digital Community Recognition",
                description=(
                    "The sponsor receives agreed recognition through selected "
                    "digital initiative communications."
                ),
                sponsor_value=(
                    "The sponsor receives documented digital visibility tied "
                    "to community arts participation."
                ),
                audience_value=(
                    "Audiences receive useful initiative and sponsor information."
                ),
                delivery_method=(
                    "Publish approved recognition through selected digital channels."
                ),
                capacity="Multiple",
                exclusivity="Non-exclusive",
                measurement_method=(
                    "Retain links, screenshots, dates, and available metrics."
                ),
                recommended_for_categories=[
                    "financial-services",
                    "healthcare",
                    "local-retail",
                ],
            ),
        ]
    )

    priorities = ResearchPrioritySet(
        priorities=[
            ResearchPriorityRecommendation(
                category_slug="financial-services",
                priority=1,
                ideal_sponsor_profile=(
                    "A regional institution with documented community investment."
                ),
                research_direction=(
                    "Identify institutions supporting education, families, "
                    "community development, or financial wellness."
                ),
                qualification_signals=[
                    "Published community investment program",
                ],
                verification_requirements=[
                    "Verify the current official sponsorship contact route",
                ],
                disqualification_signals=[
                    "No evidence of local community investment",
                ],
                recommended_asset_names=[
                    "Community Arts Activity Partner",
                    "Digital Community Recognition",
                ],
                outreach_angle=(
                    "Connect accessible arts participation with documented "
                    "community investment priorities."
                ),
            ),
            ResearchPriorityRecommendation(
                category_slug="healthcare",
                priority=2,
                ideal_sponsor_profile=(
                    "A provider with family or community education priorities."
                ),
                research_direction=(
                    "Identify providers with current public community benefit "
                    "or education programs."
                ),
                qualification_signals=[
                    "Published community education initiatives",
                ],
                verification_requirements=[
                    "Verify local decision-making authority",
                ],
                disqualification_signals=[
                    "No relevant community-facing activity",
                ],
                recommended_asset_names=[
                    "Community Arts Activity Partner",
                    "Digital Community Recognition",
                ],
                outreach_angle=(
                    "Connect family arts participation with credible community "
                    "wellbeing and education priorities."
                ),
            ),
            ResearchPriorityRecommendation(
                category_slug="local-retail",
                priority=3,
                ideal_sponsor_profile=(
                    "A family-serving retailer active in the local community."
                ),
                research_direction=(
                    "Identify retailers with local operations and documented "
                    "community event participation."
                ),
                qualification_signals=[
                    "Recent local event partnerships",
                ],
                verification_requirements=[
                    "Verify the correct local or regional contact route",
                ],
                disqualification_signals=[
                    "No local presence or relevant audience alignment",
                ],
                recommended_asset_names=[
                    "Festival Welcome Partner",
                    "Digital Community Recognition",
                ],
                outreach_angle=(
                    "Connect neighborhood visibility with a useful family and "
                    "community arts experience."
                ),
            ),
        ]
    )

    return SponsorshipIntelligenceResult(
        organization_analysis=analysis,
        sponsorship_strategy=strategy,
        sponsor_categories=categories,
        sponsorship_assets=assets,
        research_priorities=priorities,
    )


def test_persistence_saves_complete_intelligence_package(
    organization,
    initiative,
    intelligence_result,
):
    session = MagicMock()
    session.scalar.return_value = None

    record = persist_sponsorship_intelligence(
        organization,
        initiative,
        intelligence_result,
        session=session,
    )

    assert isinstance(record, SponsorshipIntelligence)

    added_records = [
        item.args[0]
        for item in session.add.call_args_list
    ]

    assert sum(
        isinstance(item, SponsorshipIntelligence)
        for item in added_records
    ) == 1

    assert sum(
        isinstance(item, SponsorCategory)
        for item in added_records
    ) == 3

    assert sum(
        isinstance(item, SponsorshipAsset)
        for item in added_records
    ) == 3

    assert sum(
        isinstance(item, ResearchPriority)
        for item in added_records
    ) == 3

    assert session.execute.call_count == 3
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_persistence_updates_existing_intelligence_record(
    organization,
    initiative,
    intelligence_result,
):
    existing = SponsorshipIntelligence(
        organization_id=organization.id,
        initiative_id=initiative.id,
        organization_analysis_json="{}",
        sponsorship_strategy_json="{}",
    )

    session = MagicMock()
    session.scalar.return_value = existing

    record = persist_sponsorship_intelligence(
        organization,
        initiative,
        intelligence_result,
        session=session,
    )

    assert record is existing

    analysis = json.loads(
        existing.organization_analysis_json
    )

    strategy = json.loads(
        existing.sponsorship_strategy_json
    )

    assert analysis["target_audiences"] == ["Families"]
    assert strategy["strategic_theme"] == (
        "Accessible arts and community participation"
    )

    added_records = [
        item.args[0]
        for item in session.add.call_args_list
    ]

    assert not any(
        isinstance(item, SponsorshipIntelligence)
        for item in added_records
    )

    session.commit.assert_called_once()


def test_category_fields_are_mapped(
    organization,
    initiative,
    intelligence_result,
):
    session = MagicMock()
    session.scalar.return_value = None

    persist_sponsorship_intelligence(
        organization,
        initiative,
        intelligence_result,
        session=session,
    )

    category = next(
        item.args[0]
        for item in session.add.call_args_list
        if isinstance(item.args[0], SponsorCategory)
    )

    assert category.slug == "financial-services"
    assert category.priority == 1
    assert category.score == 91
    assert "regional financial institution" in (
        category.ideal_sponsor_profile
    )


def test_asset_json_fields_are_mapped(
    organization,
    initiative,
    intelligence_result,
):
    session = MagicMock()
    session.scalar.return_value = None

    persist_sponsorship_intelligence(
        organization,
        initiative,
        intelligence_result,
        session=session,
    )

    asset = next(
        item.args[0]
        for item in session.add.call_args_list
        if isinstance(item.args[0], SponsorshipAsset)
    )

    assert asset.name == "Community Arts Activity Partner"
    assert asset.value == asset.sponsor_value
    assert json.loads(
        asset.recommended_categories_json
    ) == [
        "financial-services",
        "healthcare",
    ]


def test_research_priority_json_fields_are_mapped(
    organization,
    initiative,
    intelligence_result,
):
    session = MagicMock()
    session.scalar.return_value = None

    persist_sponsorship_intelligence(
        organization,
        initiative,
        intelligence_result,
        session=session,
    )

    priority = next(
        item.args[0]
        for item in session.add.call_args_list
        if isinstance(item.args[0], ResearchPriority)
    )

    assert priority.category_slug == "financial-services"
    assert json.loads(
        priority.qualification_signals_json
    ) == [
        "Published community investment program",
    ]

    assert json.loads(
        priority.recommended_asset_names_json
    ) == [
        "Community Arts Activity Partner",
        "Digital Community Recognition",
    ]


def test_unsaved_organization_is_rejected(
    initiative,
    intelligence_result,
):
    organization = SimpleNamespace(
        id=None,
        name="Unsaved Organization",
    )

    session = MagicMock()

    with pytest.raises(
        SponsorshipIntelligencePersistenceError,
        match="organization must be saved",
    ):
        persist_sponsorship_intelligence(
            organization,
            initiative,
            intelligence_result,
            session=session,
        )

    session.commit.assert_not_called()


def test_initiative_ownership_is_enforced(
    organization,
    intelligence_result,
):
    initiative = SimpleNamespace(
        id=20,
        organization_id=999,
    )

    session = MagicMock()

    with pytest.raises(
        SponsorshipIntelligencePersistenceError,
        match="does not belong",
    ):
        persist_sponsorship_intelligence(
            organization,
            initiative,
            intelligence_result,
            session=session,
        )

    session.commit.assert_not_called()


def test_invalid_result_is_rejected(
    organization,
    initiative,
):
    session = MagicMock()

    with pytest.raises(
        SponsorshipIntelligencePersistenceError,
        match="validated SponsorshipIntelligenceResult",
    ):
        persist_sponsorship_intelligence(
            organization,
            initiative,
            {"invalid": "result"},
            session=session,
        )

    session.commit.assert_not_called()


def test_transaction_rolls_back_when_database_operation_fails(
    organization,
    initiative,
    intelligence_result,
):
    session = MagicMock()
    session.scalar.return_value = None
    session.execute.side_effect = RuntimeError(
        "Simulated database failure"
    )

    with pytest.raises(
        SponsorshipIntelligencePersistenceError,
        match="transaction could not be completed",
    ):
        persist_sponsorship_intelligence(
            organization,
            initiative,
            intelligence_result,
            session=session,
        )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
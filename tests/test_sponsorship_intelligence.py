"""Tests for the sponsorship intelligence orchestrator."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from services.organization_analysis import OrganizationAnalysis
from services.research_priorities import ResearchPrioritySet
from services.sponsor_categories import SponsorCategorySet
from services.sponsorship_assets import SponsorshipAssetSet
from services.sponsorship_intelligence import (
    SponsorshipIntelligenceError,
    SponsorshipIntelligenceResult,
    generate_sponsorship_intelligence,
)
from services.sponsorship_strategy import SponsorshipStrategy


@pytest.fixture
def organization():
    """Return an organization-compatible test object."""

    return SimpleNamespace(
        name="Community Arts Center",
        organization_type="Nonprofit",
        location="Durham, NC",
        mission="Providing affordable arts education.",
        website="https://example.org",
    )


@pytest.fixture
def initiative():
    """Return a sponsorship initiative-compatible test object."""

    return SimpleNamespace(
        name="Summer Arts Festival",
        fundraising_target="$50,000",
        deadline=None,
        audience="Families and community residents",
        needs="Financial sponsors and in-kind support",
        goals="Expand community arts programming",
    )


@pytest.fixture
def analysis():
    """Return a constructed OrganizationAnalysis result.

    The individual worker test suite already validates the complete schema.
    These orchestrator tests focus only on workflow coordination.
    """

    return OrganizationAnalysis.model_construct()


@pytest.fixture
def strategy():
    """Return a constructed SponsorshipStrategy result."""

    return SponsorshipStrategy.model_construct()


@pytest.fixture
def categories():
    """Return a constructed SponsorCategorySet result."""

    return SponsorCategorySet.model_construct()


@pytest.fixture
def assets():
    """Return a constructed SponsorshipAssetSet result."""

    return SponsorshipAssetSet.model_construct()


@pytest.fixture
def research_priorities():
    """Return a constructed ResearchPrioritySet result."""

    return ResearchPrioritySet.model_construct()


def test_orchestrator_runs_workers_in_dependency_order(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
    research_priorities,
):
    """Workers must execute in the required dependency order."""

    execution_order = []

    def analysis_worker(*args, **kwargs):
        execution_order.append("organization_analysis")
        return analysis

    def strategy_worker(*args, **kwargs):
        execution_order.append("sponsorship_strategy")
        return strategy

    def category_worker(*args, **kwargs):
        execution_order.append("sponsor_categories")
        return categories

    def asset_worker(*args, **kwargs):
        execution_order.append("sponsorship_assets")
        return assets

    def research_worker(*args, **kwargs):
        execution_order.append("research_priorities")
        return research_priorities

    result = generate_sponsorship_intelligence(
        organization,
        initiative,
        organization_analysis_worker=analysis_worker,
        sponsorship_strategy_worker=strategy_worker,
        sponsor_category_worker=category_worker,
        sponsorship_asset_worker=asset_worker,
        research_priority_worker=research_worker,
    )

    assert execution_order == [
        "organization_analysis",
        "sponsorship_strategy",
        "sponsor_categories",
        "sponsorship_assets",
        "research_priorities",
    ]

    assert isinstance(result, SponsorshipIntelligenceResult)


def test_orchestrator_returns_all_worker_results(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
    research_priorities,
):
    """The aggregate result must contain every worker result."""

    result = generate_sponsorship_intelligence(
        organization,
        initiative,
        organization_analysis_worker=Mock(return_value=analysis),
        sponsorship_strategy_worker=Mock(return_value=strategy),
        sponsor_category_worker=Mock(return_value=categories),
        sponsorship_asset_worker=Mock(return_value=assets),
        research_priority_worker=Mock(
            return_value=research_priorities
        ),
    )

    assert result.organization_analysis is analysis
    assert result.sponsorship_strategy is strategy
    assert result.sponsor_categories is categories
    assert result.sponsorship_assets is assets
    assert result.research_priorities is research_priorities


def test_orchestrator_passes_dependencies_to_workers(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
    research_priorities,
):
    """Each worker must receive all required upstream results."""

    client = object()
    model = "test-model"

    analysis_worker = Mock(return_value=analysis)
    strategy_worker = Mock(return_value=strategy)
    category_worker = Mock(return_value=categories)
    asset_worker = Mock(return_value=assets)
    research_worker = Mock(return_value=research_priorities)

    generate_sponsorship_intelligence(
        organization,
        initiative,
        client=client,
        model=model,
        organization_analysis_worker=analysis_worker,
        sponsorship_strategy_worker=strategy_worker,
        sponsor_category_worker=category_worker,
        sponsorship_asset_worker=asset_worker,
        research_priority_worker=research_worker,
    )

    analysis_worker.assert_called_once_with(
        organization,
        initiative,
        client=client,
        model=model,
    )

    strategy_worker.assert_called_once_with(
        organization,
        initiative,
        analysis,
        client=client,
        model=model,
    )

    category_worker.assert_called_once_with(
        organization,
        initiative,
        analysis,
        strategy,
        client=client,
        model=model,
    )

    asset_worker.assert_called_once_with(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        client=client,
        model=model,
    )

    research_worker.assert_called_once_with(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        assets,
        client=client,
        model=model,
    )


@pytest.mark.parametrize(
    "failing_worker",
    [
        "analysis",
        "strategy",
        "categories",
        "assets",
        "research",
    ],
)
def test_worker_failure_is_wrapped(
    failing_worker,
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
    research_priorities,
):
    """Any worker failure must become an orchestrator error."""

    workers = {
        "analysis": Mock(return_value=analysis),
        "strategy": Mock(return_value=strategy),
        "categories": Mock(return_value=categories),
        "assets": Mock(return_value=assets),
        "research": Mock(return_value=research_priorities),
    }

    workers[failing_worker].side_effect = RuntimeError(
        "Simulated worker failure"
    )

    with pytest.raises(
        SponsorshipIntelligenceError,
        match="workflow could not be completed",
    ):
        generate_sponsorship_intelligence(
            organization,
            initiative,
            organization_analysis_worker=workers["analysis"],
            sponsorship_strategy_worker=workers["strategy"],
            sponsor_category_worker=workers["categories"],
            sponsorship_asset_worker=workers["assets"],
            research_priority_worker=workers["research"],
        )


def test_workflow_stops_after_failure(
    organization,
    initiative,
    analysis,
):
    """Downstream workers must not run after an upstream failure."""

    analysis_worker = Mock(return_value=analysis)
    strategy_worker = Mock(
        side_effect=RuntimeError("Strategy generation failed")
    )
    category_worker = Mock()
    asset_worker = Mock()
    research_worker = Mock()

    with pytest.raises(SponsorshipIntelligenceError):
        generate_sponsorship_intelligence(
            organization,
            initiative,
            organization_analysis_worker=analysis_worker,
            sponsorship_strategy_worker=strategy_worker,
            sponsor_category_worker=category_worker,
            sponsorship_asset_worker=asset_worker,
            research_priority_worker=research_worker,
        )

    analysis_worker.assert_called_once()
    strategy_worker.assert_called_once()
    category_worker.assert_not_called()
    asset_worker.assert_not_called()
    research_worker.assert_not_called()


def test_invalid_worker_result_is_rejected(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    research_priorities,
):
    """The aggregate model must reject an invalid worker result."""

    with pytest.raises(
        SponsorshipIntelligenceError,
        match="could not be validated",
    ):
        generate_sponsorship_intelligence(
            organization,
            initiative,
            organization_analysis_worker=Mock(
                return_value=analysis
            ),
            sponsorship_strategy_worker=Mock(
                return_value=strategy
            ),
            sponsor_category_worker=Mock(
                return_value=categories
            ),
            sponsorship_asset_worker=Mock(
                return_value={"invalid": "asset result"}
            ),
            research_priority_worker=Mock(
                return_value=research_priorities
            ),
        )


def test_result_is_immutable(
    analysis,
    strategy,
    categories,
    assets,
    research_priorities,
):
    """Completed intelligence results must not be mutated."""

    result = SponsorshipIntelligenceResult(
        organization_analysis=analysis,
        sponsorship_strategy=strategy,
        sponsor_categories=categories,
        sponsorship_assets=assets,
        research_priorities=research_priorities,
    )

    with pytest.raises(ValidationError):
        result.sponsorship_strategy = strategy


def test_orchestrator_does_not_require_flask_context(
    organization,
    initiative,
    analysis,
    strategy,
    categories,
    assets,
    research_priorities,
):
    """The service must operate without a Flask application context."""

    result = generate_sponsorship_intelligence(
        organization,
        initiative,
        organization_analysis_worker=Mock(return_value=analysis),
        sponsorship_strategy_worker=Mock(return_value=strategy),
        sponsor_category_worker=Mock(return_value=categories),
        sponsorship_asset_worker=Mock(return_value=assets),
        research_priority_worker=Mock(
            return_value=research_priorities
        ),
    )

    assert isinstance(result, SponsorshipIntelligenceResult)
    
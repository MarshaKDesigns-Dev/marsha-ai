"""Coordinate the complete sponsorship intelligence workflow.

This service runs the production sponsorship intelligence workers in dependency
order and returns one validated aggregate result.

The service does not write to the database and does not interact with Flask or
the user interface.
"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError

from services.organization_analysis import (
    OrganizationAnalysis,
    analyze_organization,
)
from services.openai_generation_timeout import (
    ClockCallable,
    GenerationStepTimeoutError,
    WORKFLOW_TIME_BUDGET_SECONDS,
    remaining_request_timeout,
)
from services.research_priorities import ResearchPrioritySet
from services.sponsor_eligibility import SponsorEligibilityAnalysis
from services.sponsor_eligibility_engine import (
    generate_sponsor_eligibility_analysis,
)
from services.sponsor_categories import (
    SponsorCategorySet,
    generate_sponsor_categories,
)
from services.sponsorship_assets import (
    SponsorshipAssetSet,
    generate_sponsorship_assets,
)
from services.sponsorship_strategy import (
    SponsorshipStrategy,
    generate_sponsorship_strategy,
)


class SponsorshipIntelligenceError(RuntimeError):
    """Raised when the sponsorship intelligence workflow cannot complete."""


class SponsorshipIntelligenceTimeoutError(SponsorshipIntelligenceError):
    """Raised when an intelligence worker exceeds its API deadline."""

    def __init__(self, timeout: GenerationStepTimeoutError) -> None:
        super().__init__("The sponsorship intelligence workflow timed out.")
        self.generation_step = timeout.generation_step
        self.step_elapsed_seconds = timeout.step_elapsed_seconds
        self.workflow_elapsed_seconds = timeout.workflow_elapsed_seconds


class SponsorshipIntelligenceResult(BaseModel):
    """Validated aggregate result returned by the orchestrator."""

    model_config = ConfigDict(frozen=True)

    organization_analysis: OrganizationAnalysis
    sponsorship_strategy: SponsorshipStrategy
    sponsor_categories: SponsorCategorySet
    sponsorship_assets: SponsorshipAssetSet
    sponsor_eligibility: SponsorEligibilityAnalysis | None = None
    research_priorities: ResearchPrioritySet | None = None


OrganizationAnalysisWorker = Callable[..., OrganizationAnalysis]
SponsorshipStrategyWorker = Callable[..., SponsorshipStrategy]
SponsorCategoryWorker = Callable[..., SponsorCategorySet]
SponsorshipAssetWorker = Callable[..., SponsorshipAssetSet]
SponsorEligibilityEngineCallable = Callable[..., SponsorEligibilityAnalysis]
LifecycleLogger = Callable[[str], None]


def generate_sponsorship_intelligence(
    organization: Any,
    initiative: Any,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    organization_analysis_worker: OrganizationAnalysisWorker = (
        analyze_organization
    ),
    sponsorship_strategy_worker: SponsorshipStrategyWorker = (
        generate_sponsorship_strategy
    ),
    sponsor_category_worker: SponsorCategoryWorker = (
        generate_sponsor_categories
    ),
    sponsorship_asset_worker: SponsorshipAssetWorker = (
        generate_sponsorship_assets
    ),
    sponsor_eligibility_engine: SponsorEligibilityEngineCallable = (
        generate_sponsor_eligibility_analysis
    ),
    workflow_budget_seconds: float = WORKFLOW_TIME_BUDGET_SECONDS,
    clock: ClockCallable = monotonic,
    lifecycle_logger: LifecycleLogger | None = None,
) -> SponsorshipIntelligenceResult:
    """Run all sponsorship intelligence workers in dependency order.

    Args:
        organization:
            An Organization model instance or compatible object.

        initiative:
            A SponsorshipInitiative model instance or compatible object.

        client:
            Optional shared OpenAI client passed to every worker.

        model:
            Optional OpenAI model override passed to every worker.

        organization_analysis_worker:
            Injectable Organization Analysis worker.

        sponsorship_strategy_worker:
            Injectable Sponsorship Strategy worker.

        sponsor_category_worker:
            Injectable Sponsor Category worker.

        sponsorship_asset_worker:
            Injectable Sponsorship Asset worker.

        sponsor_eligibility_engine:
            Injectable deterministic Sponsor Eligibility Engine.

    Returns:
        A validated SponsorshipIntelligenceResult containing the output from
        all four initial-workflow workers.

    Raises:
        SponsorshipIntelligenceError:
            If any worker fails or the aggregate result cannot be validated.
    """

    workflow_started_at = clock()

    def request_timeout_for(generation_step: str) -> float:
        return remaining_request_timeout(
            generation_step=generation_step,
            organization=organization,
            initiative=initiative,
            workflow_started_at=workflow_started_at,
            workflow_budget_seconds=workflow_budget_seconds,
            clock=clock,
        )

    def log_lifecycle(event: str) -> None:
        if lifecycle_logger is not None:
            lifecycle_logger(event)

    try:
        log_lifecycle("organization_analysis_started")
        analysis_options = {
            "client": client,
            "model": model,
            "request_timeout": request_timeout_for("organization_analysis"),
            "workflow_started_at": workflow_started_at,
        }
        if lifecycle_logger is not None:
            analysis_options["lifecycle_logger"] = lifecycle_logger
        analysis = organization_analysis_worker(
            organization,
            initiative,
            **analysis_options,
        )
        log_lifecycle("organization_analysis_completed")

        log_lifecycle("strategy_generation_started")
        strategy = sponsorship_strategy_worker(
            organization,
            initiative,
            analysis,
            client=client,
            model=model,
            request_timeout=request_timeout_for("sponsorship_strategy"),
            workflow_started_at=workflow_started_at,
        )
        log_lifecycle("strategy_generation_completed")

        log_lifecycle("sponsor_categories_started")
        categories = sponsor_category_worker(
            organization,
            initiative,
            analysis,
            strategy,
            client=client,
            model=model,
            request_timeout=request_timeout_for("sponsor_categories"),
            workflow_started_at=workflow_started_at,
        )
        log_lifecycle("sponsor_categories_completed")

        log_lifecycle("sponsorship_assets_started")
        assets = sponsorship_asset_worker(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
            client=client,
            model=model,
            request_timeout=request_timeout_for("sponsorship_assets"),
            workflow_started_at=workflow_started_at,
        )
        log_lifecycle("sponsorship_assets_completed")

        log_lifecycle("sponsor_eligibility_started")
        eligibility = sponsor_eligibility_engine(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
            assets,
        )
        log_lifecycle("sponsor_eligibility_completed")

        return SponsorshipIntelligenceResult(
            organization_analysis=analysis,
            sponsorship_strategy=strategy,
            sponsor_categories=categories,
            sponsorship_assets=assets,
            sponsor_eligibility=eligibility,
        )

    except GenerationStepTimeoutError as exc:
        raise SponsorshipIntelligenceTimeoutError(exc) from exc

    except ValidationError as exc:
        raise SponsorshipIntelligenceError(
            "The sponsorship intelligence result could not be validated."
        ) from exc

    except Exception as exc:
        raise SponsorshipIntelligenceError(
            "The sponsorship intelligence workflow could not be completed."
        ) from exc

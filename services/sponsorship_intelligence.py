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
from services.research_priorities import (
    ResearchPrioritySet,
    generate_research_priorities,
)
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

    def __init__(
        self,
        message: str,
        *,
        generation_step: str | None = None,
        error_code: str = "generation_failed",
        failure_details: dict[str, Any] | None = None,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.generation_step = generation_step
        self.error_code = error_code
        self.failure_details = failure_details or {}
        self.user_message = (
            user_message
            or "The strategy workflow stopped unexpectedly. Please try again."
        )


class SponsorshipIntelligenceTimeoutError(SponsorshipIntelligenceError):
    """Raised when an intelligence worker exceeds its API deadline."""

    def __init__(self, timeout: GenerationStepTimeoutError) -> None:
        super().__init__("The sponsorship intelligence workflow timed out.")
        self.generation_step = timeout.generation_step
        self.step_elapsed_seconds = timeout.step_elapsed_seconds
        self.workflow_elapsed_seconds = timeout.workflow_elapsed_seconds


def _classify_failure(
    exc: Exception,
    generation_step: str | None,
) -> tuple[str, str, dict[str, Any]]:
    """Classify a chained exception without exposing provider content."""

    chain = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__

    names = {type(item).__name__ for item in chain}
    details: dict[str, Any] = {
        "exception_type": type(exc).__name__,
    }
    for item in chain:
        request_id = getattr(item, "request_id", None)
        status_code = getattr(item, "status_code", None)
        if request_id:
            details["provider_request_id"] = str(request_id)
        if isinstance(status_code, int):
            details["provider_http_status"] = status_code

    if "RateLimitError" in names:
        return (
            "provider_rate_limit",
            "The AI service rate limit was reached. Please try again shortly.",
            details,
        )
    if names & {"AuthenticationError", "PermissionDeniedError"}:
        return (
            "provider_configuration_error",
            "The AI service is not configured for this request. Contact support.",
            details,
        )
    if names & {"APIConnectionError", "InternalServerError"}:
        return (
            "provider_unavailable",
            "The AI service was temporarily unavailable. Please try again.",
            details,
        )
    if names & {
        "ContentFilterFinishReasonError",
        "SafetyRefusalError",
    }:
        return (
            "provider_safety_refusal",
            "The AI service declined this request for safety reasons.",
            details,
        )
    if "ValidationError" in names:
        return (
            "schema_validation_failed",
            "The AI response did not match the required structure.",
            details,
        )
    if "ResearchPriorityGenerationError" in names:
        return (
            "research_priorities_invalid",
            "Research priorities did not pass the required evidence and reference checks.",
            details,
        )
    if any(name.endswith("GenerationError") for name in names):
        return (
            "structured_output_invalid",
            "The AI response did not pass the required validation checks.",
            details,
        )
    return (
        "generation_failed",
        "The strategy workflow stopped unexpectedly. Please try again.",
        details,
    )


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
ResearchPriorityWorker = Callable[..., ResearchPrioritySet]
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
    research_priority_worker: ResearchPriorityWorker = (
        generate_research_priorities
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

        research_priority_worker:
            Injectable Research Priority worker.

    Returns:
        A validated SponsorshipIntelligenceResult containing the output from
        every intelligence worker.

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

    current_step: str | None = None
    try:
        current_step = "organization_analysis"
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

        current_step = "sponsorship_strategy"
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

        current_step = "sponsor_categories"
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

        current_step = "sponsorship_assets"
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

        current_step = "sponsor_eligibility"
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

        current_step = "research_priorities"
        log_lifecycle("research_priorities_started")
        research_priorities = research_priority_worker(
            organization,
            initiative,
            analysis,
            strategy,
            categories,
            assets,
            client=client,
            model=model,
            request_timeout=request_timeout_for("research_priorities"),
            workflow_started_at=workflow_started_at,
        )
        log_lifecycle("research_priorities_completed")

        return SponsorshipIntelligenceResult(
            organization_analysis=analysis,
            sponsorship_strategy=strategy,
            sponsor_categories=categories,
            sponsorship_assets=assets,
            sponsor_eligibility=eligibility,
            research_priorities=research_priorities,
        )

    except GenerationStepTimeoutError as exc:
        raise SponsorshipIntelligenceTimeoutError(exc) from exc

    except ValidationError as exc:
        raise SponsorshipIntelligenceError(
            "The AI response did not match the required structure.",
            generation_step=current_step,
            error_code="schema_validation_failed",
            failure_details={"exception_type": type(exc).__name__},
            user_message="The AI response did not match the required structure.",
        ) from exc

    except Exception as exc:
        error_code, safe_message, details = _classify_failure(
            exc,
            current_step,
        )
        raise SponsorshipIntelligenceError(
            safe_message,
            generation_step=current_step,
            error_code=error_code,
            failure_details=details,
            user_message=safe_message,
        ) from exc

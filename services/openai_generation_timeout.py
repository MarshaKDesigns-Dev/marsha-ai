"""Shared timeout handling for sponsorship intelligence OpenAI requests."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic
from typing import Any

from openai import APITimeoutError, OpenAI


OPENAI_REQUEST_TIMEOUT_SECONDS = 45.0
WORKFLOW_TIME_BUDGET_SECONDS = 100.0

ClockCallable = Callable[[], float]
logger = logging.getLogger(__name__)


class GenerationStepTimeoutError(RuntimeError):
    """Raised when a generation step exceeds the available workflow time."""

    def __init__(
        self,
        generation_step: str,
        *,
        step_elapsed_seconds: float,
        workflow_elapsed_seconds: float,
    ) -> None:
        super().__init__(f"Generation step timed out: {generation_step}")
        self.generation_step = generation_step
        self.step_elapsed_seconds = step_elapsed_seconds
        self.workflow_elapsed_seconds = workflow_elapsed_seconds


def _log_timeout(
    *,
    generation_step: str,
    organization: Any,
    initiative: Any,
    step_elapsed_seconds: float,
    workflow_elapsed_seconds: float,
) -> None:
    organization_id = getattr(organization, "id", None)
    initiative_id = getattr(initiative, "id", None)
    rounded_step_elapsed = round(step_elapsed_seconds, 3)
    rounded_workflow_elapsed = round(workflow_elapsed_seconds, 3)
    extra = {
        "generation_step": generation_step,
        "organization_id": organization_id,
        "initiative_id": initiative_id,
        "step_elapsed_seconds": rounded_step_elapsed,
        "workflow_elapsed_seconds": rounded_workflow_elapsed,
    }

    logger.warning(
        "openai_generation_step_timed_out",
        extra=extra,
    )

    logger.warning(
        (
            "openai_generation_step_timed_out "
            "generation_step=%s organization_id=%s initiative_id=%s "
            "step_elapsed_seconds=%s workflow_elapsed_seconds=%s"
        ),
        generation_step,
        organization_id,
        initiative_id,
        rounded_step_elapsed,
        rounded_workflow_elapsed,
        extra=extra,
    )


def remaining_request_timeout(
    *,
    generation_step: str,
    organization: Any,
    initiative: Any,
    workflow_started_at: float,
    workflow_budget_seconds: float = WORKFLOW_TIME_BUDGET_SECONDS,
    clock: ClockCallable = monotonic,
) -> float:
    """Return the request allowance or fail before starting another worker."""

    workflow_elapsed = max(0.0, clock() - workflow_started_at)
    remaining = workflow_budget_seconds - workflow_elapsed

    if remaining <= 0:
        _log_timeout(
            generation_step=generation_step,
            organization=organization,
            initiative=initiative,
            step_elapsed_seconds=0.0,
            workflow_elapsed_seconds=workflow_elapsed,
        )
        raise GenerationStepTimeoutError(
            generation_step,
            step_elapsed_seconds=0.0,
            workflow_elapsed_seconds=workflow_elapsed,
        )

    return min(OPENAI_REQUEST_TIMEOUT_SECONDS, remaining)


def parse_with_timeout(
    *,
    client: OpenAI,
    generation_step: str,
    organization: Any,
    initiative: Any,
    request_timeout: float,
    workflow_started_at: float | None,
    clock: ClockCallable = monotonic,
    **request_options: Any,
) -> Any:
    """Run one structured OpenAI request with consistent timeout handling."""

    step_started_at = clock()
    effective_workflow_started_at = (
        step_started_at
        if workflow_started_at is None
        else workflow_started_at
    )

    try:
        request_client = client.with_options(
            timeout=min(OPENAI_REQUEST_TIMEOUT_SECONDS, request_timeout),
            max_retries=0,
        )
        return request_client.responses.parse(**request_options)
    except APITimeoutError as exc:
        finished_at = clock()
        step_elapsed = max(0.0, finished_at - step_started_at)
        workflow_elapsed = max(
            0.0,
            finished_at - effective_workflow_started_at,
        )
        _log_timeout(
            generation_step=generation_step,
            organization=organization,
            initiative=initiative,
            step_elapsed_seconds=step_elapsed,
            workflow_elapsed_seconds=workflow_elapsed,
        )
        raise GenerationStepTimeoutError(
            generation_step,
            step_elapsed_seconds=step_elapsed,
            workflow_elapsed_seconds=workflow_elapsed,
        ) from exc

"""Workspace application service for generating sponsorship intelligence.

This application service coordinates the existing sponsorship intelligence
orchestrator and persistence layer in response to a workspace generation
request. It loads the organization and initiative, verifies preconditions,
applies an explicit overwrite rule, runs the orchestrator, persists the
validated result, and returns a structured, UI-ready service result.

The service does not render templates, redirect the browser, flash messages,
read request data, call individual intelligence workers, or expose raw AI
provider output. It is independent of Flask route concerns and is fully
testable through injected dependencies.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openai import OpenAI

from services.sponsorship_intelligence import (
    SponsorshipIntelligenceError,
    SponsorshipIntelligenceResult,
    SponsorshipIntelligenceTimeoutError,
    generate_sponsorship_intelligence,
)
from services.sponsorship_intelligence_persistence import (
    SponsorshipIntelligencePersistenceError,
    persist_sponsorship_intelligence,
)

# Service result statuses. These are stable identifiers a route or caller can
# branch on without parsing user-facing message text.
STATUS_GENERATED = "generated"
STATUS_ORGANIZATION_NOT_FOUND = "organization_not_found"
STATUS_INITIATIVE_NOT_FOUND = "initiative_not_found"
STATUS_OWNERSHIP_MISMATCH = "ownership_mismatch"
STATUS_ALREADY_EXISTS = "already_exists"
STATUS_GENERATION_TIMEOUT = "generation_timeout"
STATUS_GENERATION_FAILED = "generation_failed"
STATUS_PERSISTENCE_FAILED = "persistence_failed"


@dataclass(frozen=True)
class GenerationResult:
    """Structured, UI-ready result of a workspace generation request.

    This follows the Service Result Pattern: a route can inspect ``success``
    and ``status`` to make a simple decision without reimplementing any
    business logic, and can show ``message`` directly to the user.
    """

    success: bool
    status: str
    message: str
    data: SponsorshipIntelligenceResult | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    record_id: int | None = None
    created_at: datetime | None = None
    generation_step: str | None = None


OrchestratorCallable = Callable[..., SponsorshipIntelligenceResult]
PersistCallable = Callable[..., Any]
LoadOrganizationCallable = Callable[[int], Any]
LoadInitiativeCallable = Callable[[int], Any]
IntelligenceExistsCallable = Callable[[Any], bool]
ClockCallable = Callable[[], datetime]


def _default_load_organization(organization_id: int) -> Any:
    """Load an Organization by primary key from the application database."""

    from app import Organization

    return Organization.query.get(organization_id)


def _default_load_initiative(initiative_id: int) -> Any:
    """Load a SponsorshipInitiative by primary key from the database."""

    from app import SponsorshipInitiative

    return SponsorshipInitiative.query.get(initiative_id)


def _default_intelligence_exists(initiative: Any) -> bool:
    """Return whether persisted intelligence already exists for an initiative."""

    from app import SponsorshipIntelligence

    return (
        SponsorshipIntelligence.query.filter_by(
            initiative_id=getattr(initiative, "id", None)
        ).first()
        is not None
    )


def generate_workspace_intelligence(
    organization_id: int,
    initiative_id: int,
    *,
    regenerate: bool = False,
    client: OpenAI | None = None,
    model: str | None = None,
    orchestrator: OrchestratorCallable = generate_sponsorship_intelligence,
    persist: PersistCallable = persist_sponsorship_intelligence,
    load_organization: LoadOrganizationCallable = _default_load_organization,
    load_initiative: LoadInitiativeCallable = _default_load_initiative,
    intelligence_exists: IntelligenceExistsCallable = (
        _default_intelligence_exists
    ),
    workflow_budget_seconds: float | None = None,
    now: ClockCallable = datetime.utcnow,
) -> GenerationResult:
    """Generate and persist sponsorship intelligence for a workspace request.

    The organization and initiative are loaded and validated, an explicit
    overwrite rule is applied, the existing AI Orchestrator produces a
    validated intelligence result, and that result is persisted. A structured
    ``GenerationResult`` is always returned; expected domain and persistence
    failures are translated into controlled results rather than raised.

    Args:
        organization_id:
            Primary key of the organization the intelligence is generated for.

        initiative_id:
            Primary key of the sponsorship initiative being processed.

        regenerate:
            When False (default), existing intelligence for the initiative is
            preserved and the request is refused. When True, existing
            intelligence is replaced.

        client:
            Optional shared OpenAI client passed through to the orchestrator.

        model:
            Optional OpenAI model override passed through to the orchestrator.

        orchestrator:
            Injectable orchestrator callable. Defaults to the production
            sponsorship intelligence orchestrator.

        persist:
            Injectable persistence callable. Defaults to the production
            sponsorship intelligence persistence function.

        load_organization:
            Injectable organization loader. Defaults to a database lookup.

        load_initiative:
            Injectable initiative loader. Defaults to a database lookup.

        intelligence_exists:
            Injectable existence check used by the overwrite rule. Defaults to
            a database lookup.

        now:
            Injectable timestamp provider. Defaults to ``datetime.utcnow``.

    Returns:
        A ``GenerationResult`` describing the outcome.
    """

    organization = load_organization(organization_id)
    if organization is None:
        return GenerationResult(
            success=False,
            status=STATUS_ORGANIZATION_NOT_FOUND,
            message="The requested organization could not be found.",
            errors=[STATUS_ORGANIZATION_NOT_FOUND],
        )

    initiative = load_initiative(initiative_id)
    if initiative is None:
        return GenerationResult(
            success=False,
            status=STATUS_INITIATIVE_NOT_FOUND,
            message=(
                "The requested sponsorship initiative could not be found."
            ),
            errors=[STATUS_INITIATIVE_NOT_FOUND],
        )

    if getattr(initiative, "organization_id", None) != getattr(
        organization, "id", None
    ):
        return GenerationResult(
            success=False,
            status=STATUS_OWNERSHIP_MISMATCH,
            message=(
                "The sponsorship initiative does not belong to the "
                "organization."
            ),
            errors=[STATUS_OWNERSHIP_MISMATCH],
        )

    if not regenerate and intelligence_exists(initiative):
        return GenerationResult(
            success=False,
            status=STATUS_ALREADY_EXISTS,
            message=(
                "Sponsorship intelligence already exists for this initiative. "
                "Regenerate to replace it."
            ),
            warnings=[STATUS_ALREADY_EXISTS],
        )

    try:
        orchestrator_options = {
            "client": client,
            "model": model,
        }
        if workflow_budget_seconds is not None:
            orchestrator_options["workflow_budget_seconds"] = (
                workflow_budget_seconds
            )
        result = orchestrator(
            organization,
            initiative,
            **orchestrator_options,
        )
    except SponsorshipIntelligenceTimeoutError as exc:
        return GenerationResult(
            success=False,
            status=STATUS_GENERATION_TIMEOUT,
            message=(
                "Sponsorship intelligence generation took too long. "
                "Please try again."
            ),
            errors=[STATUS_GENERATION_TIMEOUT],
            generation_step=exc.generation_step,
        )
    except SponsorshipIntelligenceError:
        return GenerationResult(
            success=False,
            status=STATUS_GENERATION_FAILED,
            message=(
                "Sponsorship intelligence could not be generated. "
                "Please try again."
            ),
            errors=[STATUS_GENERATION_FAILED],
        )

    try:
        record = persist(organization, initiative, result)
    except SponsorshipIntelligencePersistenceError:
        return GenerationResult(
            success=False,
            status=STATUS_PERSISTENCE_FAILED,
            message=(
                "Sponsorship intelligence was generated but could not be "
                "saved. Please try again."
            ),
            errors=[STATUS_PERSISTENCE_FAILED],
        )

    return GenerationResult(
        success=True,
        status=STATUS_GENERATED,
        message="Sponsorship intelligence was generated and saved.",
        data=result,
        record_id=getattr(record, "id", None),
        created_at=now(),
    )

"""Isolated unit tests for the workspace intelligence application service.

These tests exercise ``generate_workspace_intelligence`` through injected
dependencies only. No real OpenAI call and no real database access occur, so
the tests are deterministic and fast.
"""

from __future__ import annotations

from datetime import datetime

from services.generate_sponsorship_intelligence import (
    STATUS_ALREADY_EXISTS,
    STATUS_GENERATED,
    STATUS_GENERATION_FAILED,
    STATUS_GENERATION_TIMEOUT,
    STATUS_INITIATIVE_NOT_FOUND,
    STATUS_ORGANIZATION_NOT_FOUND,
    STATUS_OWNERSHIP_MISMATCH,
    STATUS_PERSISTENCE_FAILED,
    GenerationResult,
    generate_workspace_intelligence,
)
from services.sponsorship_intelligence import (
    SponsorshipIntelligenceError,
    SponsorshipIntelligenceTimeoutError,
)
from services.sponsorship_intelligence_persistence import (
    SponsorshipIntelligencePersistenceError,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, 0)

# The application service treats the orchestrator result as an opaque value it
# passes to persistence and returns in ``data``. A sentinel avoids building the
# full nested Pydantic result in these unit tests.
SENTINEL_RESULT = object()


class FakeOrganization:
    def __init__(self, id: int = 1) -> None:
        self.id = id


class FakeInitiative:
    def __init__(self, id: int = 10, organization_id: int = 1) -> None:
        self.id = id
        self.organization_id = organization_id


class FakeRecord:
    def __init__(self, id: int = 99) -> None:
        self.id = id


def make_deps(**overrides):
    """Build a full set of injected dependencies plus a call counter."""

    calls = {"orchestrator": 0, "persist": 0}
    organization = FakeOrganization()
    initiative = FakeInitiative()

    def orchestrator(org, init, *, client=None, model=None):
        calls["orchestrator"] += 1
        return SENTINEL_RESULT

    def persist(org, init, result, *, session=None):
        calls["persist"] += 1
        return FakeRecord()

    deps = dict(
        orchestrator=orchestrator,
        persist=persist,
        load_organization=lambda organization_id: organization,
        load_initiative=lambda initiative_id: initiative,
        intelligence_exists=lambda init: False,
        now=lambda: FIXED_TIME,
    )
    deps.update(overrides)
    return deps, calls


def test_happy_path_generates_and_persists():
    deps, calls = make_deps()

    result = generate_workspace_intelligence(1, 10, **deps)

    assert isinstance(result, GenerationResult)
    assert result.success is True
    assert result.status == STATUS_GENERATED
    assert result.data is SENTINEL_RESULT
    assert result.record_id == 99
    assert result.created_at == FIXED_TIME
    assert calls == {"orchestrator": 1, "persist": 1}


def test_missing_organization_stops_before_generation():
    deps, calls = make_deps(load_organization=lambda organization_id: None)

    result = generate_workspace_intelligence(1, 10, **deps)

    assert result.success is False
    assert result.status == STATUS_ORGANIZATION_NOT_FOUND
    assert calls == {"orchestrator": 0, "persist": 0}


def test_missing_initiative_stops_before_generation():
    deps, calls = make_deps(load_initiative=lambda initiative_id: None)

    result = generate_workspace_intelligence(1, 10, **deps)

    assert result.success is False
    assert result.status == STATUS_INITIATIVE_NOT_FOUND
    assert calls == {"orchestrator": 0, "persist": 0}


def test_ownership_mismatch_is_rejected():
    deps, calls = make_deps(
        load_initiative=lambda initiative_id: FakeInitiative(
            id=10, organization_id=999
        )
    )

    result = generate_workspace_intelligence(1, 10, **deps)

    assert result.success is False
    assert result.status == STATUS_OWNERSHIP_MISMATCH
    assert calls == {"orchestrator": 0, "persist": 0}


def test_existing_intelligence_blocks_without_regenerate():
    deps, calls = make_deps(intelligence_exists=lambda init: True)

    result = generate_workspace_intelligence(1, 10, **deps)

    assert result.success is False
    assert result.status == STATUS_ALREADY_EXISTS
    assert calls == {"orchestrator": 0, "persist": 0}


def test_regenerate_overwrites_existing_intelligence():
    deps, calls = make_deps(intelligence_exists=lambda init: True)

    result = generate_workspace_intelligence(1, 10, regenerate=True, **deps)

    assert result.success is True
    assert result.status == STATUS_GENERATED
    assert calls == {"orchestrator": 1, "persist": 1}


def test_generation_failure_returns_controlled_result():
    def failing_orchestrator(org, init, *, client=None, model=None):
        calls["orchestrator"] += 1
        raise SponsorshipIntelligenceError(
            "provider exploded with sensitive internal detail"
        )

    deps, calls = make_deps(orchestrator=failing_orchestrator)

    result = generate_workspace_intelligence(1, 10, **deps)

    assert result.success is False
    assert result.status == STATUS_GENERATION_FAILED
    # The orchestrator was attempted, but persistence must not run after it.
    assert calls["orchestrator"] == 1
    assert calls["persist"] == 0
    # Raw provider detail must not leak into the user-facing message.
    assert "sensitive" not in result.message.lower()


def test_generation_timeout_returns_safe_result_without_persistence():
    def timing_out_orchestrator(org, init, *, client=None, model=None):
        calls["orchestrator"] += 1
        raise SponsorshipIntelligenceTimeoutError(
            "internal timeout detail"
        )

    deps, calls = make_deps(orchestrator=timing_out_orchestrator)

    result = generate_workspace_intelligence(1, 10, **deps)

    assert result.success is False
    assert result.status == STATUS_GENERATION_TIMEOUT
    assert result.message == (
        "Sponsorship intelligence generation took too long. "
        "Please try again."
    )
    assert calls == {"orchestrator": 1, "persist": 0}
    assert "internal" not in result.message.lower()


def test_persistence_failure_returns_controlled_result():
    def failing_persist(org, init, result, *, session=None):
        raise SponsorshipIntelligencePersistenceError("database unavailable")

    deps, calls = make_deps(persist=failing_persist)

    result = generate_workspace_intelligence(1, 10, **deps)

    assert result.success is False
    assert result.status == STATUS_PERSISTENCE_FAILED
    assert calls["orchestrator"] == 1
    assert "database unavailable" not in result.message.lower()


def test_result_is_structured_type_not_flask_or_tuple():
    deps, _ = make_deps()

    result = generate_workspace_intelligence(1, 10, **deps)

    assert isinstance(result, GenerationResult)
    assert isinstance(result.success, bool)
    assert isinstance(result.status, str)

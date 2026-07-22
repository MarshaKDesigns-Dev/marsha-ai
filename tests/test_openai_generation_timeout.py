from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from services.openai_generation_timeout import (
    GenerationStepTimeoutError,
    parse_with_timeout,
    remaining_request_timeout,
)


class SequenceClock:
    def __init__(self, *values):
        self._values = iter(values)

    def __call__(self):
        return next(self._values)


class FakeResponses:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, result=None, error=None):
        self.responses = FakeResponses(result=result, error=error)
        self.options = None

    def with_options(self, **kwargs):
        self.options = kwargs
        return self


def test_request_timeout_uses_45_second_ceiling():
    timeout = remaining_request_timeout(
        generation_step="organization_analysis",
        organization=SimpleNamespace(id=1),
        initiative=SimpleNamespace(id=10),
        workflow_started_at=10.0,
        clock=lambda: 20.0,
    )

    assert timeout == 45.0


def test_request_timeout_is_capped_by_remaining_workflow_time():
    timeout = remaining_request_timeout(
        generation_step="sponsorship_assets",
        organization=SimpleNamespace(id=1),
        initiative=SimpleNamespace(id=10),
        workflow_started_at=10.0,
        clock=lambda: 105.5,
    )

    assert timeout == pytest.approx(4.5)


def test_budget_exhaustion_raises_before_request_can_start(caplog):
    with caplog.at_level("WARNING"):
        with pytest.raises(GenerationStepTimeoutError) as exc_info:
            remaining_request_timeout(
                generation_step="research_priorities",
                organization=SimpleNamespace(id=1),
                initiative=SimpleNamespace(id=10),
                workflow_started_at=10.0,
                clock=lambda: 110.0,
            )

    assert exc_info.value.generation_step == "research_priorities"
    record = caplog.records[-1]
    assert record.generation_step == "research_priorities"
    assert record.organization_id == 1
    assert record.initiative_id == 10
    assert record.step_elapsed_seconds == 0.0
    assert record.workflow_elapsed_seconds == 100.0


def test_parse_uses_capped_timeout_and_disables_retries():
    expected = object()
    client = FakeClient(result=expected)

    result = parse_with_timeout(
        client=client,
        generation_step="sponsor_categories",
        organization=SimpleNamespace(id=1),
        initiative=SimpleNamespace(id=10),
        request_timeout=12.5,
        workflow_started_at=10.0,
        clock=lambda: 20.0,
        model="test-model",
    )

    assert result is expected
    assert client.options == {"timeout": 12.5, "max_retries": 0}


def test_parse_timeout_logs_safe_context_and_raises_typed_error(caplog):
    timeout = APITimeoutError(request=httpx.Request("POST", "https://api"))
    client = FakeClient(error=timeout)

    with caplog.at_level("WARNING"):
        with pytest.raises(GenerationStepTimeoutError) as exc_info:
            parse_with_timeout(
                client=client,
                generation_step="sponsorship_strategy",
                organization=SimpleNamespace(id=1),
                initiative=SimpleNamespace(id=10),
                request_timeout=45.0,
                workflow_started_at=10.0,
                clock=SequenceClock(20.0, 35.0),
                input="sensitive user content",
            )

    error = exc_info.value
    assert error.generation_step == "sponsorship_strategy"
    assert error.step_elapsed_seconds == 15.0
    assert error.workflow_elapsed_seconds == 25.0
    record = caplog.records[-1]
    assert record.generation_step == "sponsorship_strategy"
    assert record.organization_id == 1
    assert record.initiative_id == 10
    assert "sensitive user content" not in record.getMessage()

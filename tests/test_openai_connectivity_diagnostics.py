import time

import httpx
from openai import APITimeoutError, AuthenticationError

import diagnose_openai_connectivity as diagnostics


def _succeeds() -> None:
    return


def _never_returns() -> None:
    while True:
        time.sleep(1.0)


def _production_success(
    organization_id,
    initiative_id,
    wall_clock_limit_seconds,
    sender,
):
    sender.send(
        (
            "metadata",
            {
                "model_name": "test-model",
                "prompt_character_count": 120,
                "prompt_byte_count": 125,
                "schema_name": "OrganizationAnalysis",
                "configured_http_timeout_seconds": 45.0,
                "stage_wall_clock_limit_seconds": wall_clock_limit_seconds,
                "database_record_loaded": True,
            },
        )
    )
    sender.send(("result", "success"))
    sender.close()


def _production_hangs(
    organization_id,
    initiative_id,
    wall_clock_limit_seconds,
    sender,
):
    sender.send(
        (
            "metadata",
            {
                "model_name": "test-model",
                "prompt_character_count": 120,
                "prompt_byte_count": 125,
                "schema_name": "OrganizationAnalysis",
                "configured_http_timeout_seconds": 45.0,
                "stage_wall_clock_limit_seconds": wall_clock_limit_seconds,
                "database_record_loaded": True,
            },
        )
    )
    while True:
        time.sleep(1.0)


class _Sender:
    def __init__(self):
        self.value = None

    def send(self, value):
        self.value = value

    def close(self):
        return


def test_successful_diagnostic_runs_in_isolated_process():
    name, result, elapsed = diagnostics.run_bounded_diagnostic(
        "test_success",
        _succeeds,
        5.0,
    )

    assert name == "test_success"
    assert result == "success"
    assert elapsed < 5.0


def test_never_returning_diagnostic_is_forcibly_bounded():
    started_at = time.monotonic()
    _, result, _ = diagnostics.run_bounded_diagnostic(
        "test_timeout",
        _never_returns,
        0.1,
    )

    assert result == "timeout"
    assert time.monotonic() - started_at < 3.0


def test_exception_categories_do_not_include_exception_text():
    cases = (
        (
            APITimeoutError(
                request=httpx.Request("POST", "https://api.openai.com")
            ),
            "timeout",
        ),
        (
            AuthenticationError(
                "secret authentication detail",
                response=httpx.Response(
                    401,
                    request=httpx.Request("GET", "https://api.openai.com"),
                ),
                body=None,
            ),
            "authentication_error",
        ),
        (socket_error := OSError("secret network detail"), "network_error"),
        (RuntimeError("secret SDK detail"), "sdk_error"),
    )

    for error, expected in cases:
        sender = _Sender()

        def failing_diagnostic(error=error):
            raise error

        diagnostics._execute_diagnostic(failing_diagnostic, sender)
        assert sender.value == expected
        assert "secret" not in sender.value

    assert socket_error is not None


def test_output_contains_only_approved_fields():
    output = diagnostics.format_result("dns_resolution", "success", 1.23456)

    assert output == (
        "diagnostic=dns_resolution result=success elapsed_seconds=1.235"
    )
    assert "OPENAI_API_KEY" not in output
    assert "prompt" not in output
    assert "response" not in output
    assert "exception" not in output


def test_production_analysis_success_returns_safe_metadata():
    result, elapsed, metadata = (
        diagnostics.run_production_organization_analysis(
            1,
            2,
            wall_clock_limit_seconds=5.0,
            target=_production_success,
        )
    )

    assert result == "success"
    assert elapsed < 5.0
    assert metadata["database_record_loaded"] is True
    output = diagnostics.format_production_analysis_result(
        result,
        elapsed,
        metadata,
    )
    assert "model_name=test-model" in output
    assert "prompt_character_count=120" in output
    assert "prompt_byte_count=125" in output
    assert "schema_name=OrganizationAnalysis" in output
    assert "organization_id" not in output
    assert "initiative_id" not in output


def test_production_analysis_hang_is_forcibly_bounded_with_metadata():
    started_at = time.monotonic()
    result, _, metadata = diagnostics.run_production_organization_analysis(
        1,
        2,
        wall_clock_limit_seconds=2.0,
        target=_production_hangs,
    )

    assert result == "timeout"
    assert time.monotonic() - started_at < 5.0
    assert metadata["database_record_loaded"] is True


def test_production_analysis_output_contains_no_sensitive_fields():
    output = diagnostics.format_production_analysis_result(
        "application_error",
        1.0,
        {
            "model_name": "test-model",
            "prompt_character_count": 100,
            "prompt_byte_count": 100,
            "schema_name": "OrganizationAnalysis",
            "configured_http_timeout_seconds": 45.0,
            "stage_wall_clock_limit_seconds": 60.0,
            "database_record_loaded": False,
        },
    )

    for forbidden in (
        "OPENAI_API_KEY",
        "organization_id",
        "initiative_id",
        "prompt=",
        "response",
        "schema=",
        "exception",
        "traceback",
    ):
        assert forbidden not in output

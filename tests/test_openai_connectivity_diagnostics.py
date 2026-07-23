import time

import httpx
from openai import APITimeoutError, AuthenticationError

import diagnose_openai_connectivity as diagnostics


def _succeeds() -> None:
    return


def _never_returns() -> None:
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

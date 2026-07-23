"""Run bounded, console-only OpenAI connectivity diagnostics.

This script is intended for temporary manual use in the Railway worker shell:

    python diagnose_openai_connectivity.py

It never prints credentials, request or response content, schemas, exception
details, or tracebacks.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import socket
import ssl
import time
import warnings
from collections.abc import Callable
from typing import Literal

import openai
from openai import OpenAI
from pydantic import BaseModel


DiagnosticResult = Literal[
    "success",
    "timeout",
    "network_error",
    "authentication_error",
    "sdk_error",
]

DNS_TIMEOUT_SECONDS = 5.0
TLS_TIMEOUT_SECONDS = 10.0
API_TIMEOUT_SECONDS = 45.0
PROCESS_STOP_GRACE_SECONDS = 1.0
OPENAI_HOST = "api.openai.com"
OPENAI_PORT = 443
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


class DiagnosticParsedResponse(BaseModel):
    status: Literal["ok"]


def diagnose_dns() -> None:
    socket.getaddrinfo(
        OPENAI_HOST,
        OPENAI_PORT,
        type=socket.SOCK_STREAM,
    )


def diagnose_tls() -> None:
    context = ssl.create_default_context()
    with socket.create_connection(
        (OPENAI_HOST, OPENAI_PORT),
        timeout=TLS_TIMEOUT_SECONDS,
    ) as connection:
        connection.settimeout(TLS_TIMEOUT_SECONDS)
        with context.wrap_socket(
            connection,
            server_hostname=OPENAI_HOST,
        ):
            return


def _diagnostic_client() -> OpenAI:
    return OpenAI().with_options(
        timeout=API_TIMEOUT_SECONDS,
        max_retries=0,
    )


def diagnose_models_list() -> None:
    _diagnostic_client().models.list()


def diagnose_responses_create() -> None:
    _diagnostic_client().responses.create(
        model=DEFAULT_MODEL,
        input="Return the word OK.",
        max_output_tokens=16,
    )


def diagnose_responses_parse() -> None:
    _diagnostic_client().responses.parse(
        model=DEFAULT_MODEL,
        input="Return a JSON object whose status is ok.",
        text_format=DiagnosticParsedResponse,
        max_output_tokens=32,
    )


DIAGNOSTICS: tuple[tuple[str, Callable[[], None], float], ...] = (
    ("dns_resolution", diagnose_dns, DNS_TIMEOUT_SECONDS),
    ("tcp_tls_connection", diagnose_tls, TLS_TIMEOUT_SECONDS),
    ("authenticated_models_list", diagnose_models_list, API_TIMEOUT_SECONDS),
    ("minimal_responses_create", diagnose_responses_create, API_TIMEOUT_SECONDS),
    ("minimal_responses_parse", diagnose_responses_parse, API_TIMEOUT_SECONDS),
)


def _classify_exception(error: BaseException) -> DiagnosticResult:
    if isinstance(error, (openai.APITimeoutError, TimeoutError)):
        return "timeout"
    if isinstance(error, openai.AuthenticationError):
        return "authentication_error"
    if isinstance(
        error,
        (
            openai.APIConnectionError,
            socket.gaierror,
            ssl.SSLError,
            ConnectionError,
            OSError,
        ),
    ):
        return "network_error"
    return "sdk_error"


def _execute_diagnostic(
    diagnostic: Callable[[], None],
    sender,
) -> None:
    previous_logging_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                diagnostic()
            except BaseException as error:
                result = _classify_exception(error)
            else:
                result = "success"
    finally:
        logging.disable(previous_logging_level)

    try:
        sender.send(result)
    except BaseException:
        pass
    finally:
        sender.close()


def run_bounded_diagnostic(
    name: str,
    diagnostic: Callable[[], None],
    timeout_seconds: float,
    *,
    process_context=None,
) -> tuple[str, DiagnosticResult, float]:
    context = process_context or multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    started_at = time.monotonic()
    process = context.Process(
        target=_execute_diagnostic,
        args=(diagnostic, sender),
        daemon=False,
    )
    process.start()
    sender.close()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(PROCESS_STOP_GRACE_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(PROCESS_STOP_GRACE_SECONDS)
        result: DiagnosticResult = "timeout"
    elif receiver.poll():
        result = receiver.recv()
    else:
        result = "sdk_error"

    receiver.close()
    process.close()
    elapsed_seconds = max(0.0, time.monotonic() - started_at)
    return name, result, elapsed_seconds


def format_result(
    name: str,
    result: DiagnosticResult,
    elapsed_seconds: float,
) -> str:
    return (
        f"diagnostic={name} result={result} "
        f"elapsed_seconds={elapsed_seconds:.3f}"
    )


def main() -> None:
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    for name, diagnostic, timeout_seconds in DIAGNOSTICS:
        print(
            format_result(
                *run_bounded_diagnostic(
                    name,
                    diagnostic,
                    timeout_seconds,
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()

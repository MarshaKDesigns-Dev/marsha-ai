"""Run bounded, console-only OpenAI connectivity diagnostics.

This script is intended for temporary manual use in the Railway worker shell:

    python diagnose_openai_connectivity.py

It never prints credentials, request or response content, schemas, exception
details, or tracebacks.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import re
import socket
import ssl
import time
import warnings
from collections.abc import Callable
from typing import Literal

import openai
from openai import OpenAI
from pydantic import BaseModel
from pydantic import ValidationError


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
PRODUCTION_ANALYSIS_WALL_CLOCK_SECONDS = 60.0
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


def _safe_model_name(model_name: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9._:-]+", model_name):
        return model_name
    return "unavailable"


def _exception_chain(error: BaseException):
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _classify_production_analysis_exception(
    error: BaseException,
) -> Literal["validation_error", "api_error", "application_error"]:
    from services.openai_generation_timeout import GenerationStepTimeoutError
    from services.organization_analysis import OrganizationAnalysisError

    chain = tuple(_exception_chain(error))
    if any(isinstance(item, ValidationError) for item in chain):
        return "validation_error"
    if any(
        isinstance(item, (openai.APIError, GenerationStepTimeoutError))
        for item in chain
    ):
        return "api_error"
    if isinstance(error, OrganizationAnalysisError) and error.__cause__ is None:
        return "validation_error"
    return "application_error"


def _production_analysis_child(
    organization_id: int,
    initiative_id: int,
    wall_clock_limit_seconds: float,
    sender,
) -> None:
    previous_logging_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    metadata = {
        "model_name": _safe_model_name(DEFAULT_MODEL),
        "prompt_character_count": 0,
        "prompt_byte_count": 0,
        "schema_name": "OrganizationAnalysis",
        "configured_http_timeout_seconds": API_TIMEOUT_SECONDS,
        "stage_wall_clock_limit_seconds": wall_clock_limit_seconds,
        "database_record_loaded": False,
    }
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                from time import monotonic

                from app import Organization, SponsorshipInitiative, app, db
                from services.organization_analysis import (
                    analyze_organization,
                    build_analysis_prompt,
                )

                with app.app_context():
                    organization = db.session.get(Organization, organization_id)
                    initiative = db.session.get(
                        SponsorshipInitiative,
                        initiative_id,
                    )
                    records_match = bool(
                        organization is not None
                        and initiative is not None
                        and initiative.organization_id == organization.id
                    )
                    metadata["database_record_loaded"] = records_match
                    if not records_match:
                        sender.send(("metadata", metadata))
                        sender.send(("result", "application_error"))
                        return

                    prompt = build_analysis_prompt(organization, initiative)
                    metadata["prompt_character_count"] = len(prompt)
                    metadata["prompt_byte_count"] = len(prompt.encode("utf-8"))
                    sender.send(("metadata", metadata))

                    analyze_organization(
                        organization,
                        initiative,
                        client=None,
                        model=None,
                        request_timeout=API_TIMEOUT_SECONDS,
                        workflow_started_at=monotonic(),
                    )
            except BaseException as error:
                result = _classify_production_analysis_exception(error)
            else:
                result = "success"

            sender.send(("result", result))
    except BaseException:
        try:
            sender.send(("metadata", metadata))
            sender.send(("result", "application_error"))
        except BaseException:
            pass
    finally:
        logging.disable(previous_logging_level)
        sender.close()


def run_production_organization_analysis(
    organization_id: int,
    initiative_id: int,
    *,
    wall_clock_limit_seconds: float = PRODUCTION_ANALYSIS_WALL_CLOCK_SECONDS,
    process_context=None,
    target=_production_analysis_child,
) -> tuple[str, float, dict]:
    context = process_context or multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    started_at = time.monotonic()
    process = context.Process(
        target=target,
        args=(
            organization_id,
            initiative_id,
            wall_clock_limit_seconds,
            sender,
        ),
        daemon=False,
    )
    process.start()
    sender.close()
    process.join(wall_clock_limit_seconds)

    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(PROCESS_STOP_GRACE_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(PROCESS_STOP_GRACE_SECONDS)

    metadata = {
        "model_name": _safe_model_name(DEFAULT_MODEL),
        "prompt_character_count": 0,
        "prompt_byte_count": 0,
        "schema_name": "OrganizationAnalysis",
        "configured_http_timeout_seconds": API_TIMEOUT_SECONDS,
        "stage_wall_clock_limit_seconds": wall_clock_limit_seconds,
        "database_record_loaded": False,
    }
    result = "timeout" if timed_out else "application_error"
    while True:
        try:
            message_type, value = receiver.recv()
        except (EOFError, BrokenPipeError, OSError):
            break
        if message_type == "metadata":
            metadata = value
        elif message_type == "result" and not timed_out:
            result = value

    receiver.close()
    process.close()
    elapsed_seconds = max(0.0, time.monotonic() - started_at)
    return result, elapsed_seconds, metadata


def format_production_analysis_result(
    result: str,
    elapsed_seconds: float,
    metadata: dict,
) -> str:
    return (
        "diagnostic=production_organization_analysis "
        f"result={result} elapsed_seconds={elapsed_seconds:.3f} "
        f"model_name={metadata['model_name']} "
        "prompt_character_count="
        f"{metadata['prompt_character_count']} "
        f"prompt_byte_count={metadata['prompt_byte_count']} "
        f"schema_name={metadata['schema_name']} "
        "configured_http_timeout_seconds="
        f"{metadata['configured_http_timeout_seconds']} "
        "stage_wall_clock_limit_seconds="
        f"{metadata['stage_wall_clock_limit_seconds']} "
        "database_record_loaded="
        f"{str(metadata['database_record_loaded']).lower()}"
    )


def _parse_arguments():
    parser = argparse.ArgumentParser(add_help=True)
    subparsers = parser.add_subparsers(dest="command")
    production = subparsers.add_parser("production-organization-analysis")
    production.add_argument("--organization-id", required=True, type=int)
    production.add_argument("--initiative-id", required=True, type=int)
    return parser.parse_args()


def main() -> None:
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    arguments = _parse_arguments()
    if arguments.command == "production-organization-analysis":
        print(
            format_production_analysis_result(
                *run_production_organization_analysis(
                    arguments.organization_id,
                    arguments.initiative_id,
                )
            ),
            flush=True,
        )
        return

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

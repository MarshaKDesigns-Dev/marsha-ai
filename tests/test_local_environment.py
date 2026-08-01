"""Tests for deterministic local Flask environment tooling."""

from pathlib import Path
from unittest.mock import MagicMock
import os
import subprocess

from sqlalchemy import create_engine, inspect, text

import scripts.migrate_local as migrate_local
from app import db
from scripts.verify_local import (
    CURRENT_FIELDS,
    LEGACY_FIELDS,
    FormFieldParser,
    ROOT,
)


def test_migration_runner_has_one_explicit_order():
    assert [item[0] for item in migrate_local.MIGRATIONS] == [
        "strategy_meeting_answers",
        "strategy_meeting_assets",
        "phase1_context",
        "asset_research_assignments",
        "durable_research_assignments",
        "contact_research_jobs",
        "message_approval",
        "outreach_generation_jobs",
        "follow_up_generation_jobs",
        "sponsor_research_diagnostics",
        "research_assignment_selections",
    ]


def test_migration_runner_contains_current_additive_migrations_only():
    names = {item[0] for item in migrate_local.MIGRATIONS}

    assert {
        "durable_research_assignments",
        "outreach_generation_jobs",
        "follow_up_generation_jobs",
        "sponsor_research_diagnostics",
        "research_assignment_selections",
    } <= names
    assert "org_setup" not in names


def test_normal_runner_builds_complete_empty_database_idempotently(tmp_path):
    database_path = tmp_path / "clean-local.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    environment.pop("MARSHA_SKIP_CREATE_ALL", None)
    command = [
        str(ROOT / "venv" / "Scripts" / "python.exe"),
        str(ROOT / "scripts" / "migrate_local.py"),
    ]

    first = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True,
        check=True,
    )
    second = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True,
        check=True,
    )

    assert "FAILED:" not in first.stderr
    assert "FAILED:" not in second.stderr
    engine = create_engine(environment["DATABASE_URL"])
    inspector = inspect(engine)
    model_tables = set(db.metadata.tables)
    database_tables = set(inspector.get_table_names())
    assert database_tables == model_tables
    for table_name, table in db.metadata.tables.items():
        assert {column.name for column in table.columns} == {
            column["name"] for column in inspector.get_columns(table_name)
        }

    assert {
        "active_key", "worker_id", "lease_expires_at", "available_at",
        "attempt_count",
    } <= {
        column["name"]
        for column in inspector.get_columns("research_assignment")
    }
    assert {
        "message_approved_at", "follow_up_subject", "follow_up_message",
        "follow_up_review_notes", "follow_up_reviewed_at",
        "follow_up_completed_at",
    } <= {
        column["name"] for column in inspector.get_columns("opportunity")
    }
    assert {
        "outreach_generation_job", "follow_up_generation_job",
        "sponsor_research_diagnostic",
        "sponsor_research_candidate_diagnostic",
        "research_assignment_selection",
    } <= database_tables
    for job_table, claim_index, history_index in (
        (
            "outreach_generation_job",
            "ix_outreach_generation_claim",
            "ix_outreach_generation_history",
        ),
        (
            "follow_up_generation_job",
            "ix_follow_up_generation_claim",
            "ix_follow_up_generation_history",
        ),
    ):
        index_names = {
            item["name"] for item in inspector.get_indexes(job_table)
        }
        assert {claim_index, history_index} <= index_names
        assert any(
            set(item["column_names"]) == {"active_key"}
            for item in inspector.get_unique_constraints(job_table)
        )
        assert {
            "opportunity_id", "organization_id", "initiative_id"
        } <= {
            column
            for key in inspector.get_foreign_keys(job_table)
            for column in key["constrained_columns"]
        }

    assert {
        "ix_sponsor_research_diagnostic_assignment_history"
    } <= {
        item["name"]
        for item in inspector.get_indexes("sponsor_research_diagnostic")
    }
    assert {
        "ix_sponsor_research_candidate_diagnostic_history"
    } <= {
        item["name"]
        for item in inspector.get_indexes(
            "sponsor_research_candidate_diagnostic"
        )
    }
    selection_indexes = {
        item["name"]
        for item in inspector.get_indexes("research_assignment_selection")
    }
    assert {
        "ix_research_assignment_selection_assignment_history",
        "ix_research_assignment_selection_prospect",
    } <= selection_indexes
    assert any(
        set(item["column_names"]) == {
            "research_assignment_id", "sponsor_prospect_id"
        }
        for item in inspector.get_unique_constraints(
            "research_assignment_selection"
        )
    )
    assert {
        "research_assignment_id", "sponsor_prospect_id", "opportunity_id"
    } == {
        column
        for key in inspector.get_foreign_keys(
            "research_assignment_selection"
        )
        for column in key["constrained_columns"]
    }
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        for table_name in database_tables:
            assert connection.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')
            ).scalar_one() == 0


def test_startup_uses_the_single_normal_migration_runner():
    source = (ROOT / "scripts" / "start_local.ps1").read_text(
        encoding="utf-8"
    )

    assert source.count('Join-Path $PSScriptRoot "migrate_local.py"') == 1


def test_migration_runner_skips_already_applied_work(monkeypatch):
    runner = MagicMock()
    requirements = {"organization": {"id"}}
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["organization"]
    inspector.get_columns.return_value = [{"name": "id"}]
    monkeypatch.setattr(migrate_local, "inspect", lambda engine: inspector)
    first = migrate_local.run_migrations(
        [("example", runner, requirements)]
    )
    second = migrate_local.run_migrations(
        [("example", runner, requirements)]
    )

    assert first == [("example", "already_applied")]
    assert second == [("example", "already_applied")]
    runner.assert_not_called()


def test_repository_root_and_virtualenv_contract():
    expected = Path(__file__).resolve().parents[1]

    assert ROOT == expected
    assert (ROOT / "app.py").is_file()
    assert (ROOT / "venv" / "Scripts" / "python.exe").is_file()


def test_listener_ownership_helper_is_conservative():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "local_process.ps1"
    python = root / "venv" / "Scripts" / "python.exe"
    command = (
        f". '{script}'; "
        "$owned=[pscustomobject]@{"
        "ExecutablePath='C:\\Python314\\python.exe';"
        f"CommandLine='\"{python}\" -m flask --app app run'"
        "};"
        "$unrelated=[pscustomobject]@{"
        "ExecutablePath='C:\\Python314\\python.exe';"
        "CommandLine='python -m http.server 5000'"
        "};"
        "$worker=[pscustomobject]@{"
        "ExecutablePath='C:\\Python314\\python.exe';"
        f"CommandLine='\"{python}\" -m services.sponsorship_intelligence_worker'"
        "};"
        "$legacyOwned=[pscustomobject]@{"
        "ExecutablePath='C:\\Python314\\python.exe';"
        f"CommandLine='\"{python}\" app.py'"
        "};"
        "Write-Output (Test-MarshaLocalProcess -ProcessInfo $owned);"
        "Write-Output (Test-MarshaLocalProcess -ProcessInfo $worker);"
        "Write-Output (Test-MarshaLocalProcess -ProcessInfo $legacyOwned);"
        "Write-Output (Test-MarshaLocalProcess -ProcessInfo $unrelated)"
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.splitlines() == [
        "True",
        "True",
        "True",
        "False",
    ]


def test_process_tooling_tracks_parent_child_and_orphan_processes():
    root = Path(__file__).resolve().parents[1]
    process_script = (
        root / "scripts" / "local_process.ps1"
    ).read_text(encoding="utf-8")
    start_script = (
        root / "scripts" / "start_local.ps1"
    ).read_text(encoding="utf-8")
    stop_script = (
        root / "scripts" / "stop_local.ps1"
    ).read_text(encoding="utf-8")

    assert "ParentProcessId" in process_script
    assert "function Get-MarshaLocalProcesses" in process_script
    assert "function Stop-MarshaLocalProcesses" in process_script
    assert "Stopping orphaned Marsha AI process(es)." in start_script
    assert "-m services.sponsorship_intelligence_worker" in start_script
    assert "strategy-worker-stdout.log" in start_script
    assert "services.sponsorship_intelligence_worker" in process_script
    assert "Get-MarshaLocalProcesses" in stop_script
    assert "no Marsha AI processes remain" in stop_script


def test_strategy_route_is_unique_and_uses_repository_handler():
    from app import app

    rules = [
        rule
        for rule in app.url_map.iter_rules()
        if str(rule) == "/strategy-meeting"
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "strategy_meeting"
    assert {"GET", "POST"}.issubset(rules[0].methods)
    handler = app.view_functions[rules[0].endpoint]
    assert Path(handler.__code__.co_filename).resolve() == (
        ROOT / "app.py"
    ).resolve()


def test_strategy_form_contract_contains_only_four_current_fields():
    from app import app

    source = app.jinja_loader.get_source(
        app.jinja_env,
        "strategy_meeting.html",
    )[0]
    parser = FormFieldParser()
    parser.feed(source)
    names = set(parser.names)

    assert CURRENT_FIELDS.issubset(names)
    assert not LEGACY_FIELDS.intersection(names)


def test_verification_disables_import_time_schema_writes():
    script = (ROOT / "scripts" / "verify_local.ps1").read_text(
        encoding="utf-8"
    )
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert '$env:MARSHA_SKIP_CREATE_ALL = "1"' in script
    assert 'os.getenv("MARSHA_SKIP_CREATE_ALL") != "1"' in app_source


def test_verification_accepts_clean_first_run_strategy_redirect():
    source = (ROOT / "scripts" / "verify_local.py").read_text(
        encoding="utf-8"
    )

    assert 'strategy_final_path not in {"/strategy-meeting", "/setup"}' in source
    assert '"strategy_meeting.html"' in source

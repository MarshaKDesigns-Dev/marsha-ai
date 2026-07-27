"""Tests for deterministic local Flask environment tooling."""

from pathlib import Path
from unittest.mock import MagicMock
import subprocess

import scripts.migrate_local as migrate_local
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
    ]


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
        "Write-Output (Test-MarshaLocalProcess -ProcessInfo $owned);"
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

    assert result.stdout.splitlines() == ["True", "False"]


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
    assert "Stopping orphaned Marsha AI Flask process(es)." in start_script
    assert "Get-MarshaLocalProcesses" in stop_script


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

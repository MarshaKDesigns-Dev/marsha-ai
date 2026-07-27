"""Read-only verification of the running local Marsha AI environment."""

from __future__ import annotations

import inspect as python_inspect
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import inspect


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module  # noqa: E402
from extensions import db  # noqa: E402


CURRENT_FIELDS = {
    "strategy_top_priorities",
    "strategy_priority_sponsors",
    "strategy_success_beyond_fundraising",
    "strategy_concerns_constraints",
}
LEGACY_FIELDS = {
    "sponsorship_goals",
    "audience",
    "estimated_reach",
    "needs",
    "sponsorship_needs",
    "campaign_goals",
    "fundraising_target",
    "deadline",
}


class FormFieldParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = []

    def handle_starttag(self, tag, attrs):
        if tag not in {"input", "select", "textarea"}:
            return
        attributes = dict(attrs)
        if attributes.get("name"):
            self.names.append(attributes["name"])


def get_status_and_body(url: str) -> tuple[int, str, str]:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=5) as response:
            return (
                response.status,
                response.read().decode("utf-8"),
                response.geturl(),
            )
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), exc.geturl()


def runtime_report() -> dict:
    strategy_rules = [
        rule
        for rule in app_module.app.url_map.iter_rules()
        if str(rule) == "/strategy-meeting"
    ]
    handler = app_module.app.view_functions.get("strategy_meeting")
    with app_module.app.app_context():
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        missing_tables = set(db.metadata.tables) - existing_tables
        missing_columns = {}
        for table_name, table in db.metadata.tables.items():
            if table_name not in existing_tables:
                continue
            existing = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            missing = {column.name for column in table.columns} - existing
            if missing:
                missing_columns[table_name] = sorted(missing)
        database_path = (
            str(Path(db.engine.url.database).resolve())
            if db.engine.url.drivername.startswith("sqlite")
            else db.engine.url.database
        )

    strategy_status, _, strategy_final_url = get_status_and_body(
        "http://127.0.0.1:5000/strategy-meeting"
    )
    strategy_template = app_module.app.jinja_loader.get_source(
        app_module.app.jinja_env,
        "strategy_meeting.html",
    )[0]
    parser = FormFieldParser()
    parser.feed(strategy_template)
    rendered_names = set(parser.names)
    workspace_status, _, workspace_final_url = get_status_and_body(
        "http://127.0.0.1:5000/workspace"
    )
    strategy_final_path = urlsplit(strategy_final_url).path
    report = {
        "repository_root": str(ROOT),
        "python_executable": sys.executable,
        "app_module_file": str(Path(app_module.__file__).resolve()),
        "flask_import_name": app_module.app.import_name,
        "strategy_route_count": len(strategy_rules),
        "strategy_endpoint": (
            strategy_rules[0].endpoint if strategy_rules else None
        ),
        "strategy_handler_file": (
            str(Path(python_inspect.getsourcefile(handler)).resolve())
            if handler
            else None
        ),
        "strategy_handler_line": (
            handler.__code__.co_firstlineno if handler else None
        ),
        "database_path": database_path,
        "missing_tables": sorted(missing_tables),
        "missing_columns": missing_columns,
        "strategy_get_status": strategy_status,
        "strategy_final_path": strategy_final_path,
        "rendered_strategy_fields": sorted(
            CURRENT_FIELDS & rendered_names
        ),
        "legacy_strategy_fields": sorted(
            LEGACY_FIELDS & rendered_names
        ),
        "workspace_get_status": workspace_status,
        "workspace_final_path": urlsplit(workspace_final_url).path,
    }
    errors = []
    if ROOT != Path.cwd().resolve():
        errors.append("Verification must run from the repository root.")
    if Path(sys.executable).resolve() != (
        ROOT / "venv" / "Scripts" / "python.exe"
    ).resolve():
        errors.append("Verification is not using the repository virtualenv.")
    if Path(app_module.__file__).resolve() != (ROOT / "app.py").resolve():
        errors.append("Imported app module is not the repository app.py.")
    if len(strategy_rules) != 1:
        errors.append("Strategy Meeting route is missing or duplicated.")
    if report["strategy_handler_file"] != str((ROOT / "app.py").resolve()):
        errors.append("Strategy Meeting handler is from another source file.")
    if missing_tables or missing_columns:
        errors.append("Local database schema is behind current models.")
    if strategy_status != 200:
        errors.append("GET /strategy-meeting did not return 200.")
    if strategy_final_path not in {"/strategy-meeting", "/setup"}:
        errors.append(
            "GET /strategy-meeting reached an unexpected final route."
        )
    if CURRENT_FIELDS & rendered_names != CURRENT_FIELDS:
        errors.append("Current Strategy Meeting fields are incomplete.")
    if LEGACY_FIELDS & rendered_names:
        errors.append("Legacy Strategy Meeting fields are rendered.")
    if workspace_status not in {200, 302}:
        errors.append("GET /workspace returned an unexpected status.")
    report["errors"] = errors
    return report


def main() -> None:
    report = runtime_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

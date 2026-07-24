"""Regression tests for Flask application import entry points."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _run_isolated(script: str):
    environment = os.environ.copy()
    environment["DATABASE_URL"] = "sqlite:///:memory:"
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_job_service_import_does_not_create_second_flask_application():
    result = _run_isolated(
        """
import importlib
import sys
import app
original_module = sys.modules["app"]
original_app = app.app
jobs = importlib.import_module("services.sponsorship_intelligence_jobs")
assert sys.modules["app"] is original_module
assert app.app is original_app
assert jobs.db is app.db
"""
    )

    assert result.returncode == 0, result.stderr


def test_app_py_entry_path_workspace_uses_registered_database():
    result = _run_isolated(
        """
import runpy
from flask import Flask
Flask.run = lambda self, *args, **kwargs: None
namespace = runpy.run_module("app", run_name="__main__", alter_sys=True)
application = namespace["app"]
database = namespace["db"]
Organization = namespace["Organization"]
Initiative = namespace["SponsorshipInitiative"]
with application.app_context():
    organization = Organization(
        name="Youth Test Organization",
        organization_type="Community Group",
        city="Durham",
        state="NC",
        mission="Support youth education.",
        is_active=True,
    )
    database.session.add(organization)
    database.session.flush()
    database.session.add(
        Initiative(
            organization_id=organization.id,
            name="Family Learning Festival",
            audience="Children, youth, and families",
            needs="Program sponsorship",
            goals="Expand education access",
            status="Active",
        )
    )
    database.session.commit()
response = application.test_client().get("/workspace")
assert response.status_code == 200
from services.sponsorship_intelligence_jobs import _models
Job, service_db = _models()
assert service_db is database
assert Job is namespace["SponsorshipIntelligenceJob"]
"""
    )

    assert result.returncode == 0, result.stderr


def test_gunicorn_style_app_import_uses_shared_application():
    result = _run_isolated(
        """
import app
from application import app as shared_app
from extensions import db as shared_db
assert app.app is shared_app
assert app.db is shared_db
assert app.app.test_client().get("/").status_code == 200
"""
    )

    assert result.returncode == 0, result.stderr

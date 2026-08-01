"""Tests for the additive ResearchAssignmentSelection migration."""

from flask import Flask
from sqlalchemy import inspect, text

import migrate_research_assignment_selections as migration
from extensions import db


def test_migration_is_additive_idempotent_and_does_not_backfill(tmp_path, monkeypatch):
    database_path = tmp_path / "research-selections.db"
    test_app = Flask(__name__)
    test_app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{database_path.as_posix()}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(test_app)
    monkeypatch.setattr(migration, "app", test_app)
    with test_app.app_context():
        for statement in (
            "CREATE TABLE research_assignment (id INTEGER PRIMARY KEY)",
            "CREATE TABLE sponsor_prospect (id INTEGER PRIMARY KEY)",
            "CREATE TABLE opportunity (id INTEGER PRIMARY KEY)",
            "INSERT INTO research_assignment (id) VALUES (1)",
            "INSERT INTO sponsor_prospect (id) VALUES (2)",
            "INSERT INTO opportunity (id) VALUES (3)",
        ):
            db.session.execute(text(statement))
        db.session.commit()

    migration.run_migration()
    migration.run_migration()

    with test_app.app_context():
        inspector = inspect(db.engine)
        assert "research_assignment_selection" in inspector.get_table_names()
        assert db.session.execute(text(
            "SELECT COUNT(*) FROM research_assignment_selection"
        )).scalar_one() == 0
        assert db.session.execute(text(
            "SELECT COUNT(*) FROM opportunity"
        )).scalar_one() == 1
        index_names = {
            item["name"] for item in inspector.get_indexes(
                "research_assignment_selection"
            )
        }
        assert "ix_research_assignment_selection_assignment_history" in index_names
        assert "ix_research_assignment_selection_prospect" in index_names

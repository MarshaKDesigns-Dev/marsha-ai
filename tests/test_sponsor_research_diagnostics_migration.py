from flask import Flask
from sqlalchemy import inspect, text

import migrate_sponsor_research_diagnostics as migration
from extensions import db


def test_migration_is_additive_idempotent_and_does_not_backfill(tmp_path, monkeypatch):
    database_path = tmp_path / "diagnostics.db"
    test_app = Flask(__name__)
    test_app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{database_path.as_posix()}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(test_app)
    monkeypatch.setattr(migration, "app", test_app)
    with test_app.app_context():
        for statement in (
            "CREATE TABLE organization (id INTEGER PRIMARY KEY)",
            "CREATE TABLE sponsorship_initiative (id INTEGER PRIMARY KEY)",
            "CREATE TABLE sponsorship_asset (id INTEGER PRIMARY KEY)",
            "CREATE TABLE research_assignment (id INTEGER PRIMARY KEY, status TEXT)",
            "INSERT INTO research_assignment (id, status) VALUES (1, 'needs_attention')",
        ):
            db.session.execute(text(statement))
        db.session.commit()
    migration.run_migration()
    migration.run_migration()
    with test_app.app_context():
        inspector = inspect(db.engine)
        assert "sponsor_research_diagnostic" in inspector.get_table_names()
        assert "sponsor_research_candidate_diagnostic" in inspector.get_table_names()
        assert "outcome_code" in {
            item["name"] for item in inspector.get_columns(
                "sponsor_research_diagnostic"
            )
        }
        assert db.session.execute(text(
            "SELECT COUNT(*) FROM sponsor_research_diagnostic"
        )).scalar_one() == 0
        assert db.session.execute(text(
            "SELECT status FROM research_assignment WHERE id=1"
        )).scalar_one() == "needs_attention"

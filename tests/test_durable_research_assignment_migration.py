from flask import Flask
from sqlalchemy import inspect, text

import migrate_durable_research_assignments as migration
from extensions import db


def test_migration_is_additive_idempotent_and_preserves_existing_rows(
    tmp_path, monkeypatch,
):
    database_path = tmp_path / "durable-research.db"
    migration_app = Flask(__name__)
    migration_app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{database_path.as_posix()}"
    )
    migration_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(migration_app)
    monkeypatch.setattr(migration, "app", migration_app)
    with migration_app.app_context():
        db.session.execute(text("""
            CREATE TABLE research_assignment (
              id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL,
              initiative_id INTEGER NOT NULL, sponsorship_asset_id INTEGER NOT NULL,
              status VARCHAR(30) NOT NULL, started_at DATETIME,
              completed_at DATETIME, result_count INTEGER NOT NULL DEFAULT 0,
              results_json TEXT NOT NULL DEFAULT '[]', error_details TEXT,
              created_at DATETIME, updated_at DATETIME
            )
        """))
        db.session.execute(text("""
            INSERT INTO research_assignment
              (id, organization_id, initiative_id, sponsorship_asset_id,
               status, created_at, updated_at)
            VALUES (1, 1, 2, 3, 'completed', '2026-07-01', '2026-07-01')
        """))
        db.session.commit()

    migration.run_migration()
    migration.run_migration()

    with migration_app.app_context():
        columns = {
            column["name"]
            for column in inspect(db.engine).get_columns("research_assignment")
        }
        row = db.session.execute(text(
            "SELECT status, active_key, available_at, attempt_count "
            "FROM research_assignment WHERE id=1"
        )).one()
        indexes = {
            item["name"] for item in inspect(db.engine).get_indexes(
                "research_assignment"
            )
        }

    assert {"active_key", "worker_id", "lease_expires_at", "available_at",
            "attempt_count"} <= columns
    assert row.status == "completed"
    assert row.active_key is None
    assert row.available_at is not None
    assert row.attempt_count == 0
    assert "ux_research_assignment_active_key" in indexes

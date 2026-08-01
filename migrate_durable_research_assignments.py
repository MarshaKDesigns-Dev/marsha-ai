"""Add durable claim and lease fields to ResearchAssignment."""

from sqlalchemy import inspect, text

from app import ResearchAssignment, app, db


COLUMNS = {
    "active_key": "VARCHAR(255)",
    "worker_id": "VARCHAR(255)",
    "lease_expires_at": "TIMESTAMP",
    "available_at": "TIMESTAMP",
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
}


def run_migration() -> None:
    """Apply additive changes and preserve every historical assignment."""

    with app.app_context():
        ResearchAssignment.__table__.create(bind=db.engine, checkfirst=True)
        inspector = inspect(db.engine)
        existing = {
            column["name"]
            for column in inspector.get_columns("research_assignment")
        }
        for name, definition in COLUMNS.items():
            if name not in existing:
                db.session.execute(
                    text(
                        "ALTER TABLE research_assignment "
                        f"ADD COLUMN {name} {definition}"
                    )
                )
        db.session.execute(
            text(
                "UPDATE research_assignment SET available_at = created_at "
                "WHERE available_at IS NULL"
            )
        )
        db.session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ux_research_assignment_active_key "
                "ON research_assignment (active_key)"
            )
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_research_assignment_claim "
                "ON research_assignment "
                "(status, available_at, lease_expires_at)"
            )
        )
        db.session.commit()
        print("Durable research assignment migration complete.")


if __name__ == "__main__":
    run_migration()

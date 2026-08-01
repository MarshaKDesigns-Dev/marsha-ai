"""Create and upgrade the durable Contact Discovery job table."""

from sqlalchemy import inspect, text

from app import ContactResearchJob, app, db


COLUMNS = {
    "active_key": "VARCHAR(255)",
    "worker_id": "VARCHAR(255)",
    "lease_expires_at": "TIMESTAMP",
    "available_at": "TIMESTAMP",
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
}


def run_migration() -> None:
    """Create the Contact Discovery job schema idempotently."""

    with app.app_context():
        ContactResearchJob.__table__.create(
            bind=db.engine,
            checkfirst=True,
        )
        existing = {
            column["name"]
            for column in inspect(db.engine).get_columns("contact_research_job")
        }
        for name, definition in COLUMNS.items():
            if name not in existing:
                db.session.execute(text(
                    "ALTER TABLE contact_research_job "
                    f"ADD COLUMN {name} {definition}"
                ))
        db.session.execute(text(
            "UPDATE contact_research_job SET available_at = created_at "
            "WHERE available_at IS NULL"
        ))
        db.session.execute(text(
            "UPDATE contact_research_job SET active_key = opportunity_id "
            "WHERE status IN ('queued', 'processing') AND active_key IS NULL "
            "AND id = (SELECT MAX(active.id) FROM contact_research_job active "
            "WHERE active.opportunity_id = contact_research_job.opportunity_id "
            "AND active.status IN ('queued', 'processing'))"
        ))
        db.session.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ux_contact_research_job_active_key "
            "ON contact_research_job (active_key)"
        ))
        db.session.commit()
        for index in ContactResearchJob.__table__.indexes:
            index.create(bind=db.engine, checkfirst=True)
        print("Contact research job migration complete.")


if __name__ == "__main__":
    run_migration()

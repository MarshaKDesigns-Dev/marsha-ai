"""Add asset-scoped Research Worker assignment and pipeline fields."""

from sqlalchemy import inspect, text

from app import ResearchAssignment, app, db


COLUMNS = {
    "sponsor_prospect": {
        "sponsorship_asset_id": "INTEGER REFERENCES sponsorship_asset(id)",
    },
    "opportunity": {
        "organization_id": "INTEGER REFERENCES organization(id)",
        "initiative_id": "INTEGER REFERENCES sponsorship_initiative(id)",
        "sponsorship_asset_id": "INTEGER REFERENCES sponsorship_asset(id)",
        "sponsor_prospect_id": "INTEGER REFERENCES sponsor_prospect(id)",
    },
}


def run_migration() -> None:
    """Apply only additive, backward-compatible schema changes."""

    with app.app_context():
        ResearchAssignment.__table__.create(bind=db.engine, checkfirst=True)
        for index in ResearchAssignment.__table__.indexes:
            index.create(bind=db.engine, checkfirst=True)

        inspector = inspect(db.engine)
        for table_name, definitions in COLUMNS.items():
            existing = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            for name, definition in definitions.items():
                if name not in existing:
                    db.session.execute(
                        text(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN {name} {definition}"
                        )
                    )
        db.session.commit()
        print("Asset research assignment migration complete.")


if __name__ == "__main__":
    run_migration()

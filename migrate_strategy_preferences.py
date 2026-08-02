"""Add user-controlled audience and sponsor-category preferences."""

from sqlalchemy import inspect, text

from app import app, db


INITIATIVE_COLUMNS = {
    "audience_age_context": (
        "VARCHAR(40) DEFAULT 'unclear'"
    ),
    "sponsor_category_exclusions_json": (
        "TEXT DEFAULT '[]'"
    ),
}


def run_migration() -> None:
    """Add only nullable/defaulted preference columns, without changing data."""

    with app.app_context():
        existing = {
            item["name"]
            for item in inspect(db.engine).get_columns(
                "sponsorship_initiative"
            )
        }
        for name, definition in INITIATIVE_COLUMNS.items():
            if name not in existing:
                db.session.execute(text(
                    "ALTER TABLE sponsorship_initiative "
                    f"ADD COLUMN {name} {definition}"
                ))
        db.session.commit()
        print("Strategy preference migration complete.")


if __name__ == "__main__":
    run_migration()

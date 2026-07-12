"""Upgrade the database for generated sponsorship intelligence.

This migration:

- creates new intelligence and research-priority tables through db.create_all();
- adds missing AI-generated fields to sponsor_category;
- adds missing AI-generated fields to sponsorship_asset;
- may be run repeatedly without duplicating columns.
"""

from sqlalchemy import inspect, text

from app import app, db


SPONSOR_CATEGORY_COLUMNS = {
    "priority": "INTEGER",
    "ideal_sponsor_profile": "TEXT",
    "research_direction": "TEXT",
}


SPONSORSHIP_ASSET_COLUMNS = {
    "description": "TEXT",
    "sponsor_value": "TEXT",
    "audience_value": "TEXT",
    "delivery_method": "TEXT",
    "exclusivity": "VARCHAR(150)",
    "measurement_method": "TEXT",
    "recommended_categories_json": "TEXT DEFAULT '[]'",
}


def add_missing_columns(
    table_name: str,
    columns: dict[str, str],
) -> None:
    """Add columns that are not already present on an existing table."""

    inspector = inspect(db.engine)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    for column_name, column_type in columns.items():
        if column_name in existing_columns:
            print(f"Column already exists: {table_name}.{column_name}")
            continue

        db.session.execute(
            text(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} {column_type}"
            )
        )

        print(f"Added column: {table_name}.{column_name}")

    db.session.commit()


def run_migration() -> None:
    """Create new tables and upgrade existing intelligence tables."""

    with app.app_context():
        db.create_all()

        add_missing_columns(
            "sponsor_category",
            SPONSOR_CATEGORY_COLUMNS,
        )

        add_missing_columns(
            "sponsorship_asset",
            SPONSORSHIP_ASSET_COLUMNS,
        )

        print("Sponsorship intelligence migration complete.")


if __name__ == "__main__":
    run_migration()
    

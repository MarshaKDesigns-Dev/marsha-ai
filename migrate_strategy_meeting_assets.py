"""Add Strategy Meeting and sponsorship-asset approval fields."""

from sqlalchemy import inspect, text

from app import app, db
from migrate_phase1_context import run_migration as run_phase1_migration


INITIATIVE_COLUMNS = {
    "sponsorship_goals": "TEXT",
    "estimated_reach": "TEXT",
    "strategy_meeting_completed_at": "TIMESTAMP",
}
ASSET_COLUMNS = {
    "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'Pending'",
    "approval_updated_at": "TIMESTAMP",
    "source": "VARCHAR(20) NOT NULL DEFAULT 'generated'",
}


def _add_missing_columns(table_name, definitions):
    columns = {
        column["name"]
        for column in inspect(db.engine).get_columns(table_name)
    }
    for name, definition in definitions.items():
        if name not in columns:
            db.session.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {name} {definition}"
                )
            )


def run_migration() -> None:
    """Apply the additive Release 2 columns idempotently."""

    with app.app_context():
        _add_missing_columns(
            "sponsorship_initiative",
            INITIATIVE_COLUMNS,
        )
        _add_missing_columns(
            "sponsorship_asset",
            ASSET_COLUMNS,
        )
        db.session.commit()
        print("Strategy Meeting and asset approval migration complete.")


if __name__ == "__main__":
    run_migration()
    run_phase1_migration()

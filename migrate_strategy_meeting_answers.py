"""Add focused Strategy Meeting answer fields."""

from sqlalchemy import inspect, text

from app import app, db


INITIATIVE_COLUMNS = {
    "strategy_top_priorities": "TEXT",
    "strategy_priority_sponsors": "TEXT",
    "strategy_success_beyond_fundraising": "TEXT",
    "strategy_concerns_constraints": "TEXT",
}


def run_migration() -> None:
    """Apply the additive Strategy Meeting answer columns idempotently."""

    with app.app_context():
        existing = {
            column["name"]
            for column in inspect(db.engine).get_columns(
                "sponsorship_initiative"
            )
        }
        for name, definition in INITIATIVE_COLUMNS.items():
            if name not in existing:
                db.session.execute(
                    text(
                        "ALTER TABLE sponsorship_initiative "
                        f"ADD COLUMN {name} {definition}"
                    )
                )
        db.session.commit()
        print("Focused Strategy Meeting answer migration complete.")


if __name__ == "__main__":
    run_migration()

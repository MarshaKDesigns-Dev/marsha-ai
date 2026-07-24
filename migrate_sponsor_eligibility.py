"""Add persisted deterministic sponsor eligibility analysis."""

from sqlalchemy import inspect, text

from app import app, db


def run_migration() -> None:
    """Add the eligibility JSON column idempotently."""

    with app.app_context():
        columns = {
            column["name"]
            for column in inspect(db.engine).get_columns(
                "sponsorship_intelligence"
            )
        }
        if "sponsor_eligibility_json" not in columns:
            db.session.execute(
                text(
                    "ALTER TABLE sponsorship_intelligence "
                    "ADD COLUMN sponsor_eligibility_json TEXT"
                )
            )
            db.session.commit()
        print("Sponsor eligibility migration complete.")


if __name__ == "__main__":
    run_migration()

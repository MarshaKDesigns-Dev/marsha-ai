"""Add explicit outreach-message approval state without changing existing data."""

from sqlalchemy import inspect, text

from app import app, db


COLUMNS = {
    "message_approved_at": "DATETIME",
}


def run_migration() -> None:
    with app.app_context():
        inspector = inspect(db.engine)
        existing = {
            column["name"]
            for column in inspector.get_columns("opportunity")
        }

        for name, column_type in COLUMNS.items():
            if name in existing:
                print(f"Skipped existing column: {name}")
                continue

            db.session.execute(
                text(
                    f"ALTER TABLE opportunity "
                    f"ADD COLUMN {name} {column_type}"
                )
            )
            db.session.commit()
            print(f"Added column: {name}")

        print("Message approval migration complete.")


if __name__ == "__main__":
    run_migration()

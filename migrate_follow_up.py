from sqlalchemy import inspect, text
from app import app, db

COLUMNS = {
    "follow_up_subject": "VARCHAR(300)",
    "follow_up_message": "TEXT",
    "follow_up_review_notes": "TEXT",
    "follow_up_reviewed_at": "DATETIME",
    "follow_up_completed_at": "DATETIME",
}

with app.app_context():
    inspector = inspect(db.engine)
    existing = {column["name"] for column in inspector.get_columns("opportunity")}

    for name, column_type in COLUMNS.items():
        if name in existing:
            print(f"Skipped existing column: {name}")
            continue

        db.session.execute(
            text(f"ALTER TABLE opportunity ADD COLUMN {name} {column_type}")
        )
        db.session.commit()
        print(f"Added column: {name}")

    print("Follow-up migration complete.")

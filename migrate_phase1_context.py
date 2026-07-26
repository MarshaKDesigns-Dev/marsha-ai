"""Add the additive Phase 1 customer-context and recommendation fields."""

from sqlalchemy import inspect, text

from app import app, db


COLUMNS = {
    "organization": {
        "current_sponsors_json": "TEXT DEFAULT '[]'",
        "existing_relationships_json": "TEXT DEFAULT '[]'",
        "businesses_already_contacted_json": "TEXT DEFAULT '[]'",
        "businesses_never_contact_json": "TEXT DEFAULT '[]'",
    },
    "sponsorship_initiative": {
        "sponsorship_needs_json": "TEXT DEFAULT '[]'",
        "sponsorship_needs_other": "TEXT",
        "sponsorship_needs_notes": "TEXT",
        "desired_sponsor_categories_json": "TEXT DEFAULT '[]'",
        "geographic_scope": "VARCHAR(50)",
        "geographic_radius_miles": "INTEGER",
        "dream_sponsors_json": "TEXT DEFAULT '[]'",
    },
    "sponsorship_intelligence_job": {
        "failure_details_json": "TEXT",
    },
    "sponsor_prospect": {
        "verified_information_json": "TEXT NOT NULL DEFAULT '[]'",
        "why_recommended": "TEXT",
        "organization_fit": "TEXT",
        "recommended_ask": "TEXT",
        "contribution_type": "VARCHAR(50)",
        "why_may_say_yes": "TEXT",
        "why_may_say_yes_evidence_json": "TEXT NOT NULL DEFAULT '[]'",
        "recommendation_strength": "VARCHAR(20)",
        "recommendation_strength_score": "INTEGER",
        "strength_factors_json": "TEXT NOT NULL DEFAULT '{}'",
    },
}


def run_migration() -> None:
    with app.app_context():
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
        print("Phase 1 customer-context migration complete.")


if __name__ == "__main__":
    run_migration()

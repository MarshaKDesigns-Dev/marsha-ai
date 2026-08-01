"""Create additive Sponsor Research diagnostic tables."""

from sqlalchemy import inspect, text

from app import (
    SponsorResearchCandidateDiagnostic,
    SponsorResearchDiagnostic,
    app,
    db,
)


def run_migration() -> None:
    """Create only the diagnostic tables; never fabricate history."""

    with app.app_context():
        SponsorResearchDiagnostic.__table__.create(
            bind=db.engine, checkfirst=True
        )
        SponsorResearchCandidateDiagnostic.__table__.create(
            bind=db.engine, checkfirst=True
        )
        columns = {
            item["name"]
            for item in inspect(db.engine).get_columns(
                "sponsor_research_diagnostic"
            )
        }
        if "outcome_code" not in columns:
            db.session.execute(text(
                "ALTER TABLE sponsor_research_diagnostic "
                "ADD COLUMN outcome_code VARCHAR(100)"
            ))
            db.session.commit()
        print("Sponsor Research diagnostics migration complete.")


if __name__ == "__main__":
    run_migration()

"""Create the evidence-backed sponsor prospect table."""

from app import SponsorProspect, app, db


def run_migration() -> None:
    """Create the sponsor-prospect schema idempotently."""

    with app.app_context():
        SponsorProspect.__table__.create(
            bind=db.engine,
            checkfirst=True,
        )
        for index in SponsorProspect.__table__.indexes:
            index.create(bind=db.engine, checkfirst=True)
        print("Sponsor prospect migration complete.")


if __name__ == "__main__":
    run_migration()

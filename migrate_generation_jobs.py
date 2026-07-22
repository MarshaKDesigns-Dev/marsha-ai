"""Create the durable sponsorship intelligence job table and indexes."""

from app import SponsorshipIntelligenceJob, app, db


def run_migration() -> None:
    """Create the generation-job schema idempotently."""

    with app.app_context():
        db.create_all()
        for index in SponsorshipIntelligenceJob.__table__.indexes:
            index.create(bind=db.engine, checkfirst=True)
        print("Sponsorship intelligence job migration complete.")


if __name__ == "__main__":
    run_migration()

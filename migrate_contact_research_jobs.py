"""Create the durable Contact Discovery job table."""

from app import ContactResearchJob, app, db


def run_migration() -> None:
    """Create the Contact Discovery job schema idempotently."""

    with app.app_context():
        ContactResearchJob.__table__.create(
            bind=db.engine,
            checkfirst=True,
        )
        for index in ContactResearchJob.__table__.indexes:
            index.create(bind=db.engine, checkfirst=True)
        print("Contact research job migration complete.")


if __name__ == "__main__":
    run_migration()

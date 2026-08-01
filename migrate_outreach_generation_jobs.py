"""Create the durable Outreach generation job table idempotently."""

from app import OutreachGenerationJob, app, db


def run_migration():
    with app.app_context():
        OutreachGenerationJob.__table__.create(bind=db.engine, checkfirst=True)
        for index in OutreachGenerationJob.__table__.indexes:
            index.create(bind=db.engine, checkfirst=True)
        print("Outreach generation job migration complete.")


if __name__ == "__main__":
    run_migration()

"""Create durable Follow-Up generation jobs idempotently."""
from app import FollowUpGenerationJob, app, db
def run_migration():
    with app.app_context():
        FollowUpGenerationJob.__table__.create(bind=db.engine, checkfirst=True)
        for index in FollowUpGenerationJob.__table__.indexes:
            index.create(bind=db.engine, checkfirst=True)
        print("Follow-Up generation job migration complete.")
if __name__ == "__main__":
    run_migration()

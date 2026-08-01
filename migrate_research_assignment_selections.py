"""Create the additive ResearchAssignmentSelection table."""

from app import ResearchAssignmentSelection, app, db


def run_migration() -> None:
    """Create selection history without fabricating historical links."""

    with app.app_context():
        ResearchAssignmentSelection.__table__.create(
            bind=db.engine, checkfirst=True
        )
        print("Research assignment selection migration complete.")


if __name__ == "__main__":
    run_migration()

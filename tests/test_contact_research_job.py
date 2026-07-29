from datetime import datetime

from flask import Flask
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

import migrate_contact_research_jobs as migration
from app import ContactResearchJob, Opportunity
from extensions import db


def test_contact_research_job_lifecycle_and_history_persist():
    engine = create_engine("sqlite:///:memory:")
    Opportunity.__table__.create(bind=engine)
    ContactResearchJob.__table__.create(bind=engine)
    started = datetime(2026, 7, 28, 12, 0, 0)
    completed = datetime(2026, 7, 28, 12, 2, 0)

    with Session(engine) as session:
        opportunity = Opportunity(parent_prospect="Example Sponsor")
        session.add(opportunity)
        session.flush()
        first = ContactResearchJob(
            opportunity=opportunity,
            status="completed",
            result_json='{"result_type":"general_contact"}',
            provider_response_id="resp_contact_1",
            input_tokens=100,
            output_tokens=50,
            started_at=started,
            completed_at=completed,
        )
        second = ContactResearchJob(
            opportunity=opportunity,
            status="failed",
            error_message="No verified contact was found.",
            started_at=completed,
            completed_at=completed,
        )
        session.add_all([first, second])
        session.commit()

        saved = (
            session.query(ContactResearchJob)
            .filter_by(opportunity_id=opportunity.id)
            .order_by(ContactResearchJob.id)
            .all()
        )

        assert len(saved) == 2
        assert saved[0].status == "completed"
        assert saved[0].provider_response_id == "resp_contact_1"
        assert saved[0].input_tokens == 100
        assert saved[0].output_tokens == 50
        assert saved[0].started_at == started
        assert saved[0].completed_at == completed
        assert saved[1].status == "failed"
        assert saved[1].error_message == "No verified contact was found."
        assert saved[0].opportunity is opportunity
        assert opportunity.contact_research_jobs == saved


def test_contact_research_job_migration_is_additive_and_idempotent(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "contact-research-migration.db"
    migration_app = Flask(__name__)
    migration_app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{database_path.as_posix()}"
    )
    migration_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(migration_app)
    monkeypatch.setattr(migration, "app", migration_app)

    migration.run_migration()
    migration.run_migration()

    with migration_app.app_context():
        inspector = inspect(db.engine)
        columns = {
            column["name"]
            for column in inspector.get_columns("contact_research_job")
        }

    assert columns == {
        "id",
        "opportunity_id",
        "status",
        "error_message",
        "result_json",
        "provider_response_id",
        "input_tokens",
        "output_tokens",
        "created_at",
        "started_at",
        "completed_at",
    }

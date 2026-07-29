from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect

import migrate_message_approval as migration


def test_message_approval_migration_is_additive_and_idempotent(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "message-approval.db"
    migration_app = Flask(__name__)
    migration_app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{database_path.as_posix()}"
    )
    migration_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    migration_db = SQLAlchemy(migration_app)

    with migration_app.app_context():
        migration_db.session.execute(
            migration_db.text(
                "CREATE TABLE opportunity "
                "(id INTEGER PRIMARY KEY, parent_prospect VARCHAR(200))"
            )
        )
        migration_db.session.execute(
            migration_db.text(
                "INSERT INTO opportunity (id, parent_prospect) "
                "VALUES (16, 'Packaging Express')"
            )
        )
        migration_db.session.commit()

    monkeypatch.setattr(migration, "app", migration_app)
    monkeypatch.setattr(migration, "db", migration_db)

    migration.run_migration()
    migration.run_migration()

    with migration_app.app_context():
        columns = {
            column["name"]
            for column in inspect(migration_db.engine).get_columns(
                "opportunity"
            )
        }
        preserved = migration_db.session.execute(
            migration_db.text(
                "SELECT parent_prospect, message_approved_at "
                "FROM opportunity WHERE id = 16"
            )
        ).one()

    assert "message_approved_at" in columns
    assert preserved == ("Packaging Express", None)

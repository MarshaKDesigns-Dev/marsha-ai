"""Tests for the narrowly scoped application-data reset command."""

from unittest.mock import MagicMock, patch

import pytest

from reset_application_data import (
    CONFIRMATION,
    application_table_names,
    clear_application_data,
    database_identity,
    run,
    verify_application_data_empty,
    verify_database_integrity,
)


def test_reset_scope_contains_only_application_model_tables():
    assert set(application_table_names()) == {
        "organization",
        "contact_research_job",
        "opportunity",
        "outreach_generation_job",
        "follow_up_generation_job",
        "research_assignment",
        "research_assignment_selection",
        "research_priority",
        "research_record",
        "sponsor_category",
        "sponsor_prospect",
        "sponsor_research_candidate_diagnostic",
        "sponsor_research_diagnostic",
        "sponsorship_asset",
        "sponsorship_initiative",
        "sponsorship_intelligence",
        "sponsorship_intelligence_job",
    }
    assert "alembic_version" not in application_table_names()


def test_execute_requires_exact_confirmation():
    with pytest.raises(ValueError):
        run(execute=True, confirmation=None)

    with pytest.raises(ValueError):
        run(execute=True, confirmation="reset")

    assert CONFIRMATION == "RESET-APPLICATION-DATA"


def test_reset_verification_rejects_any_remaining_application_rows():
    verify_application_data_empty({"organization": 0, "opportunity": 0})

    with pytest.raises(RuntimeError, match="organization"):
        verify_application_data_empty(
            {"organization": 1, "opportunity": 0}
        )


def test_database_identity_does_not_include_credentials():
    with __import__("app").app.app_context():
        identity = database_identity()

    assert set(identity).issubset({"driver", "database", "host"})
    assert "password" not in identity


def test_integrity_verification_preserves_schema_and_checks_foreign_keys():
    connection = MagicMock()
    connection.dialect.name = "sqlite"
    connection.execute.return_value = []

    with __import__("app").app.app_context():
        from extensions import db

        expected = list(db.metadata.tables)

    inspector = MagicMock()
    inspector.get_table_names.return_value = expected
    with patch(
        "reset_application_data.inspect",
        return_value=inspector,
    ):
        result = verify_database_integrity(connection)

    assert result == {
        "schema_verified": True,
        "foreign_key_violations": [],
    }


def test_postgresql_reset_uses_transaction_safe_truncate_and_identity_reset():
    connection = MagicMock()
    connection.dialect.name = "postgresql"
    connection.dialect.identifier_preparer.quote.side_effect = (
        lambda value: f'"{value}"'
    )

    clear_application_data(connection)

    statement = str(connection.execute.call_args.args[0])
    assert statement.startswith("TRUNCATE TABLE")
    assert '"organization"' in statement
    assert '"sponsorship_intelligence_job"' in statement
    assert statement.endswith("RESTART IDENTITY CASCADE")
    assert "DROP" not in statement

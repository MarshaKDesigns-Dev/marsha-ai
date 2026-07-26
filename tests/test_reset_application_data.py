"""Tests for the narrowly scoped application-data reset command."""

from unittest.mock import MagicMock

import pytest

from reset_application_data import (
    CONFIRMATION,
    application_table_names,
    clear_application_data,
    run,
)


def test_reset_scope_contains_only_application_model_tables():
    assert set(application_table_names()) == {
        "organization",
        "opportunity",
        "research_priority",
        "research_record",
        "sponsor_category",
        "sponsor_prospect",
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

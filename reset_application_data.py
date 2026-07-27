"""Inventory or transactionally clear Marsha AI application data.

This command operates only on tables declared by the application's SQLAlchemy
models. It does not drop tables, alter schema, touch migration bookkeeping, or
change service configuration.

Usage:
    python reset_application_data.py
    python reset_application_data.py --execute --confirm RESET-APPLICATION-DATA
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import delete, func, inspect, select, text

from app import app, db


CONFIRMATION = "RESET-APPLICATION-DATA"


def application_tables():
    """Return every application model table in foreign-key-safe order."""

    return tuple(db.metadata.sorted_tables)


def application_table_names() -> tuple[str, ...]:
    return tuple(table.name for table in application_tables())


def record_counts(connection) -> dict[str, int]:
    return {
        table.name: connection.scalar(
            select(func.count()).select_from(table)
        )
        for table in application_tables()
    }


def database_identity() -> dict[str, str]:
    """Return a secret-safe description of the configured reset target."""

    url = db.engine.url
    if url.drivername.startswith("sqlite"):
        return {
            "driver": url.drivername,
            "database": str(Path(url.database).resolve()),
        }
    return {
        "driver": url.drivername,
        "database": url.database or "",
        "host": url.host or "",
    }


def verify_application_data_empty(counts: dict[str, int]) -> None:
    """Fail the reset if any model-backed application rows remain."""

    remaining = {
        table_name: count
        for table_name, count in counts.items()
        if count
    }
    if remaining:
        raise RuntimeError(
            f"Application-data reset verification failed: {remaining}"
        )


def verify_database_integrity(connection) -> dict:
    """Verify application tables remain and SQLite has no FK violations."""

    existing_tables = set(inspect(connection).get_table_names())
    missing_tables = set(application_table_names()) - existing_tables
    if missing_tables:
        raise RuntimeError(
            f"Reset removed required schema tables: {sorted(missing_tables)}"
        )
    foreign_key_violations = []
    if connection.dialect.name == "sqlite":
        foreign_key_violations = [
            list(row)
            for row in connection.execute(
                text("PRAGMA foreign_key_check")
            )
        ]
    if foreign_key_violations:
        raise RuntimeError(
            "Foreign-key verification failed after reset."
        )
    return {
        "schema_verified": True,
        "foreign_key_violations": foreign_key_violations,
    }


def clear_application_data(connection) -> None:
    """Clear model-backed records and reset identities in one transaction."""

    tables = application_tables()
    if connection.dialect.name == "postgresql":
        preparer = connection.dialect.identifier_preparer
        names = ", ".join(
            preparer.quote(table.name)
            for table in tables
        )
        connection.execute(
            text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE")
        )
        return

    for table in reversed(tables):
        connection.execute(delete(table))

    if connection.dialect.name == "sqlite":
        sequence_exists = connection.scalar(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = 'sqlite_sequence'"
            )
        )
        if sequence_exists:
            connection.execute(
                text("DELETE FROM sqlite_sequence")
            )


def run(*, execute: bool, confirmation: str | None) -> dict:
    if execute and confirmation != CONFIRMATION:
        raise ValueError(
            f"--execute requires --confirm {CONFIRMATION}"
        )

    with app.app_context():
        if not execute:
            with db.engine.connect() as connection:
                before = record_counts(connection)
            return {
                "mode": "inventory",
                "database": database_identity(),
                "tables": application_table_names(),
                "before": before,
                "execute_command": (
                    "python reset_application_data.py --execute "
                    f"--confirm {CONFIRMATION}"
                ),
            }

        with db.engine.begin() as connection:
            before = record_counts(connection)
            clear_application_data(connection)
            after = record_counts(connection)
            verify_application_data_empty(after)
            integrity = verify_database_integrity(connection)

        return {
            "mode": "executed",
            "database": database_identity(),
            "tables": application_table_names(),
            "before": before,
            "after": after,
            "verified_empty": True,
            **integrity,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inventory or clear Marsha AI application records."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the transactional application-data reset.",
    )
    parser.add_argument(
        "--confirm",
        help=f"Required with --execute: {CONFIRMATION}",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(execute=args.execute, confirmation=args.confirm),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

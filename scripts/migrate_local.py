"""Run the current additive local migrations in one verified order."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    ContactResearchJob,
    FollowUpGenerationJob,
    OutreachGenerationJob,
    ResearchAssignment,
    ResearchAssignmentSelection,
    SponsorResearchCandidateDiagnostic,
    SponsorResearchDiagnostic,
    app,
    db,
)
from migrate_asset_research_assignments import (  # noqa: E402
    COLUMNS as ASSET_RESEARCH_COLUMNS,
    run_migration as run_asset_research_migration,
)
from migrate_contact_research_jobs import (  # noqa: E402
    run_migration as run_contact_research_job_migration,
)
from migrate_durable_research_assignments import (  # noqa: E402
    COLUMNS as DURABLE_RESEARCH_COLUMNS,
    run_migration as run_durable_research_migration,
)
from migrate_follow_up_generation_jobs import (  # noqa: E402
    run_migration as run_follow_up_generation_job_migration,
)
from migrate_message_approval import (  # noqa: E402
    COLUMNS as MESSAGE_APPROVAL_COLUMNS,
    run_migration as run_message_approval_migration,
)
from migrate_phase1_context import (  # noqa: E402
    COLUMNS as PHASE1_COLUMNS,
    run_migration as run_phase1_migration,
)
from migrate_outreach_generation_jobs import (  # noqa: E402
    run_migration as run_outreach_generation_job_migration,
)
from migrate_research_assignment_selections import (  # noqa: E402
    run_migration as run_research_assignment_selection_migration,
)
from migrate_sponsor_research_diagnostics import (  # noqa: E402
    run_migration as run_sponsor_research_diagnostics_migration,
)
from migrate_strategy_meeting_answers import (  # noqa: E402
    INITIATIVE_COLUMNS as STRATEGY_ANSWER_COLUMNS,
    run_migration as run_strategy_answer_migration,
)
from migrate_strategy_meeting_assets import (  # noqa: E402
    ASSET_COLUMNS,
    INITIATIVE_COLUMNS as STRATEGY_ASSET_COLUMNS,
    run_migration as run_strategy_asset_migration,
)


# app.py's guarded create_all supplies the model tables on a brand-new local
# database. This explicit order upgrades older databases without seed data:
# foundational setup fields first, Research before its durable/diagnostic
# dependants, Opportunity approval before its generation jobs, and selection
# history only after Research, Sponsor Prospect, and Opportunity are present.
MIGRATIONS = (
    (
        "strategy_meeting_answers",
        run_strategy_answer_migration,
        {"sponsorship_initiative": set(STRATEGY_ANSWER_COLUMNS)},
    ),
    (
        "strategy_meeting_assets",
        run_strategy_asset_migration,
        {
            "sponsorship_initiative": set(STRATEGY_ASSET_COLUMNS),
            "sponsorship_asset": set(ASSET_COLUMNS),
        },
    ),
    (
        "phase1_context",
        run_phase1_migration,
        {
            table_name: set(columns)
            for table_name, columns in PHASE1_COLUMNS.items()
        },
    ),
    (
        "asset_research_assignments",
        run_asset_research_migration,
        {
            **{
                table_name: set(columns)
                for table_name, columns in ASSET_RESEARCH_COLUMNS.items()
            },
            ResearchAssignment.__tablename__: {
                column.name
                for column in ResearchAssignment.__table__.columns
            },
        },
    ),
    (
        "durable_research_assignments",
        run_durable_research_migration,
        {
            ResearchAssignment.__tablename__: set(DURABLE_RESEARCH_COLUMNS),
        },
    ),
    (
        "contact_research_jobs",
        run_contact_research_job_migration,
        {
            ContactResearchJob.__tablename__: {
                column.name
                for column in ContactResearchJob.__table__.columns
            },
        },
    ),
    (
        "message_approval",
        run_message_approval_migration,
        {"opportunity": set(MESSAGE_APPROVAL_COLUMNS)},
    ),
    (
        "outreach_generation_jobs",
        run_outreach_generation_job_migration,
        {
            OutreachGenerationJob.__tablename__: {
                column.name
                for column in OutreachGenerationJob.__table__.columns
            },
        },
    ),
    (
        "follow_up_generation_jobs",
        run_follow_up_generation_job_migration,
        {
            FollowUpGenerationJob.__tablename__: {
                column.name
                for column in FollowUpGenerationJob.__table__.columns
            },
        },
    ),
    (
        "sponsor_research_diagnostics",
        run_sponsor_research_diagnostics_migration,
        {
            SponsorResearchDiagnostic.__tablename__: {
                column.name
                for column in SponsorResearchDiagnostic.__table__.columns
            },
            SponsorResearchCandidateDiagnostic.__tablename__: {
                column.name
                for column in
                SponsorResearchCandidateDiagnostic.__table__.columns
            },
        },
    ),
    (
        "research_assignment_selections",
        run_research_assignment_selection_migration,
        {
            ResearchAssignmentSelection.__tablename__: {
                column.name
                for column in ResearchAssignmentSelection.__table__.columns
            },
        },
    ),
)


def migration_is_applied(inspector, requirements) -> bool:
    """Return whether every required table and column currently exists."""

    table_names = set(inspector.get_table_names())
    for table_name, required_columns in requirements.items():
        if table_name not in table_names:
            return False
        existing = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
        if not required_columns.issubset(existing):
            return False
    return True


def run_migrations(migrations=MIGRATIONS) -> list[tuple[str, str]]:
    """Run missing migrations in order and verify every result."""

    results = []
    with app.app_context():
        for name, runner, requirements in migrations:
            inspector = inspect(db.engine)
            if migration_is_applied(inspector, requirements):
                print(f"ALREADY APPLIED: {name}")
                results.append((name, "already_applied"))
                continue
            print(f"RUNNING: {name}")
            runner()
            if not migration_is_applied(inspect(db.engine), requirements):
                raise RuntimeError(
                    f"Migration verification failed: {name}"
                )
            print(f"APPLIED: {name}")
            results.append((name, "applied"))
    return results


def main() -> None:
    try:
        run_migrations()
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

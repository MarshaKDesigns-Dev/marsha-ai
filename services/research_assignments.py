"""Durable queue operations for Sponsor Research assignments."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, or_
from sqlalchemy.exc import IntegrityError

from extensions import db

ACTIVE_STATUSES = ("ready", "working")
SAFE_FAILURE_MESSAGE = (
    "The Research Worker could not complete this assignment. No sponsors "
    "were saved. Please try again or select another sponsorship asset."
)


def _model():
    matches = [
        mapper.class_ for mapper in db.Model.registry.mappers
        if mapper.class_.__name__ == "ResearchAssignment"
    ]
    if len(matches) != 1:
        raise RuntimeError("ResearchAssignment is not registered.")
    return matches[0]


def active_assignment_key(organization_id, initiative_id, asset_id):
    return f"{organization_id}:{initiative_id}:{asset_id}"


def get_active_assignment(organization_id, initiative_id, asset_id, *, session=None):
    database_session = session or db.session
    return database_session.query(_model()).filter_by(
        active_key=active_assignment_key(
            organization_id, initiative_id, asset_id
        )
    ).first()


def enqueue_assignment(organization, initiative, asset, *, session=None, now=None):
    database_session = session or db.session
    timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    key = active_assignment_key(organization.id, initiative.id, asset.id)
    existing = get_active_assignment(
        organization.id, initiative.id, asset.id, session=database_session
    )
    if existing is not None:
        return existing, False
    Assignment = _model()
    assignment = Assignment(
        organization_id=organization.id,
        initiative_id=initiative.id,
        sponsorship_asset_id=asset.id,
        status="ready",
        active_key=key,
        available_at=timestamp,
        attempt_count=0,
    )
    database_session.add(assignment)
    try:
        database_session.commit()
        return assignment, True
    except IntegrityError:
        database_session.rollback()
        existing = get_active_assignment(
            organization.id, initiative.id, asset.id, session=database_session
        )
        if existing is None:
            raise
        return existing, False


def claim_next_assignment(worker_id, *, lease_seconds=600, max_attempts=3,
                          session=None, now=None):
    database_session = session or db.session
    Assignment = _model()
    timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    while True:
        eligible = or_(
            and_(Assignment.status == "ready", Assignment.available_at <= timestamp),
            and_(Assignment.status == "working", Assignment.lease_expires_at <= timestamp),
        )
        query = database_session.query(Assignment).filter(eligible).order_by(
            case((Assignment.status == "ready", 0), else_=1),
            Assignment.available_at.asc(),
            Assignment.id.asc(),
        )
        if database_session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        assignment = query.first()
        if assignment is None:
            database_session.rollback()
            return None
        if (assignment.attempt_count or 0) >= max_attempts:
            mark_needs_attention(
                assignment,
                "Sponsor research could not be completed after multiple attempts.",
                session=database_session,
                commit=False,
                now=timestamp,
            )
            database_session.commit()
            continue
        assignment.status = "working"
        assignment.worker_id = worker_id
        assignment.started_at = assignment.started_at or timestamp
        assignment.lease_expires_at = timestamp + timedelta(seconds=lease_seconds)
        assignment.attempt_count = (assignment.attempt_count or 0) + 1
        assignment.updated_at = timestamp
        database_session.commit()
        return assignment


def mark_completed(assignment, results, *, session=None, commit=True, now=None):
    import json
    database_session = session or db.session
    timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    assignment.results_json = json.dumps(
        [item.model_dump(mode="json") for item in results], ensure_ascii=False
    )
    assignment.result_count = len(results)
    assignment.status = "completed"
    assignment.completed_at = timestamp
    assignment.error_details = None
    assignment.active_key = None
    assignment.lease_expires_at = None
    assignment.updated_at = timestamp
    database_session.commit() if commit else database_session.flush()


def mark_needs_attention(assignment, message=SAFE_FAILURE_MESSAGE, *,
                         session=None, commit=True, now=None):
    database_session = session or db.session
    timestamp = (now or datetime.now(UTC)).replace(tzinfo=None)
    assignment.status = "needs_attention"
    assignment.completed_at = timestamp
    assignment.error_details = message
    assignment.result_count = 0
    assignment.results_json = "[]"
    assignment.active_key = None
    assignment.lease_expires_at = None
    assignment.updated_at = timestamp
    database_session.commit() if commit else database_session.flush()

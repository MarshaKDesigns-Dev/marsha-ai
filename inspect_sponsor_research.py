"""Print safe internal Sponsor Research diagnostics by assignment ID."""

from __future__ import annotations

import argparse
import json

from app import (
    ResearchAssignment,
    SponsorResearchCandidateDiagnostic,
    SponsorResearchDiagnostic,
    SponsorshipAsset,
    app,
)


def _json(value, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def build_report(assignment_id: int) -> tuple[str, int]:
    """Return a human-readable safe report and process exit status."""

    assignment = ResearchAssignment.query.filter_by(id=assignment_id).first()
    if assignment is None:
        return f"Research assignment {assignment_id} was not found.", 2
    asset = SponsorshipAsset.query.filter_by(
        id=assignment.sponsorship_asset_id
    ).first()
    diagnostics = SponsorResearchDiagnostic.query.filter_by(
        research_assignment_id=assignment.id
    ).order_by(SponsorResearchDiagnostic.created_at, SponsorResearchDiagnostic.id).all()
    lines = [
        f"Assignment: {assignment.id} ({assignment.status})",
        f"Asset: {getattr(asset, 'name', 'Unavailable')}",
    ]
    if not diagnostics:
        lines.append("Diagnostics: none (historical attempts are not backfilled).")
        return "\n".join(lines), 0
    for diagnostic in diagnostics:
        lines.extend(
            [
                "",
                f"Diagnostic: {diagnostic.id}",
                f"Provider response: {diagnostic.provider_response_id or 'unavailable'}",
                f"Outcome code: {diagnostic.outcome_code or 'unavailable'}",
                f"Search queries: {_json(diagnostic.search_queries_json, [])}",
                f"Source URLs: {_json(diagnostic.source_urls_json, [])}",
                (
                    "Counts: "
                    f"{diagnostic.candidate_count} returned, "
                    f"{diagnostic.accepted_count} accepted, "
                    f"{diagnostic.rejected_count} rejected"
                ),
            ]
        )
        candidates = SponsorResearchCandidateDiagnostic.query.filter_by(
            diagnostic_id=diagnostic.id
        ).order_by(SponsorResearchCandidateDiagnostic.id).all()
        for candidate in candidates:
            lines.extend(
                [
                    f"  [{candidate.result_status.upper()}] {candidate.candidate_name}",
                    f"    Website: {candidate.canonical_website or 'unavailable'}",
                    (
                        "    Reason codes: "
                        f"{_json(candidate.rejection_codes_json, [])}"
                    ),
                    (
                        "    Citation validation: "
                        f"{_json(candidate.citation_validation_json, {})}"
                    ),
                ]
            )
    return "\n".join(lines), 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assignment-id", type=int, required=True)
    args = parser.parse_args(argv)
    with app.app_context():
        report, status = build_report(args.assignment_id)
        print(report)
        return status


if __name__ == "__main__":
    raise SystemExit(main())

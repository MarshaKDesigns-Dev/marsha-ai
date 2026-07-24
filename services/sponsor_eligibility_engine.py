"""Deterministic Marsha AI Sponsor Eligibility Engine."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from services.sponsor_eligibility import (
    EligibilityConfidence,
    EligibilityFacts,
    EligibilityStatus,
    ExclusionSource,
    SponsorEligibilityAnalysis,
)
from services.sponsor_eligibility_rules_v1 import SponsorEligibilityRulesV1


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).strip()


def _clean_list(values: Iterable[Any] | None) -> list[str]:
    if values is None:
        return []
    return list(dict.fromkeys(_clean(value) for value in values if _clean(value)))


def normalize_eligibility_facts(
    organization: Any,
    initiative: Any,
    analysis: Any,
    strategy: Any,
    categories: Any,
    assets: Any,
    *,
    explicit_restrictions: Iterable[str] = (),
) -> EligibilityFacts:
    """Normalize current questionnaire and AI output into immutable facts."""

    category_items = getattr(categories, "categories", None) or []
    asset_items = getattr(assets, "assets", None) or []

    return EligibilityFacts(
        organization_type=_clean(
            getattr(organization, "organization_type", "")
        ),
        mission=_clean(getattr(organization, "mission", "")),
        location=_clean(getattr(organization, "location", "")),
        initiative_name=_clean(getattr(initiative, "name", "")),
        audience=_clean(getattr(initiative, "audience", "")),
        needs=_clean(getattr(initiative, "needs", "")),
        goals=_clean(getattr(initiative, "goals", "")),
        fundraising_target=_clean(
            getattr(initiative, "fundraising_target", "")
        ),
        deadline=_clean(getattr(initiative, "deadline", "")),
        analyzed_target_audiences=_clean_list(
            getattr(analysis, "target_audiences", None)
        ),
        analysis_risks_or_gaps=_clean_list(
            getattr(analysis, "risks_or_gaps", None)
        ),
        strategy_partnership_principles=_clean_list(
            getattr(strategy, "partnership_principles", None)
        ),
        strategy_sponsor_benefits=_clean_list(
            getattr(strategy, "sponsor_benefits", None)
        ),
        category_slugs=_clean_list(
            getattr(item, "slug", "")
            for item in category_items
        ),
        category_names=_clean_list(
            getattr(item, "category", "")
            for item in category_items
        ),
        category_ideal_profiles=_clean_list(
            getattr(item, "ideal_sponsor_profile", "")
            for item in category_items
        ),
        asset_names=_clean_list(
            getattr(item, "name", "")
            for item in asset_items
        ),
        explicit_restrictions=_clean_list(explicit_restrictions),
    )


def _infer_initiative_type(facts: EligibilityFacts) -> str:
    text = f"{facts.organization_type} {facts.initiative_name}".lower()
    mappings = (
        ("festival", "festival"),
        ("conference", "conference"),
        ("pageant", "pageant"),
        ("tournament", "sports_event"),
        ("league", "sports_program"),
        ("gala", "event"),
        ("event", "event"),
        ("school", "school_initiative"),
        ("program", "program"),
        ("campaign", "campaign"),
    )
    return next(
        (result for keyword, result in mappings if keyword in text),
        "sponsorship_initiative",
    )


def _infer_sensitive_categories(facts: EligibilityFacts) -> list[str]:
    text = f"{facts.mission} {facts.audience} {facts.goals}".lower()
    mappings = (
        ("health", "health"),
        ("relig", "religion"),
        ("politic", "politics"),
        ("recovery", "recovery"),
        ("addiction", "addiction"),
        ("disab", "disability"),
        ("youth", "youth"),
        ("child", "children"),
    )
    return [
        label
        for keyword, label in mappings
        if keyword in text
    ]


def _deduplicate_exclusions(exclusions):
    result = {}
    for exclusion in exclusions:
        existing = result.get(exclusion.industry_code)
        if existing is None or exclusion.source.value == "user_restriction":
            result[exclusion.industry_code] = exclusion
    return list(result.values())


class SponsorEligibilityEngine:
    """Execute Marsha AI's deterministic sponsor eligibility rules."""

    def __init__(self, ruleset=None) -> None:
        self.ruleset = ruleset or SponsorEligibilityRulesV1()

    def evaluate(
        self,
        facts: EligibilityFacts,
    ) -> SponsorEligibilityAnalysis:
        context, audits = self.ruleset.execute(facts)
        exclusions = _deduplicate_exclusions(context.exclusions)
        blocking_reasons = list(dict.fromkeys(context.blocking_reasons))
        missing_information = list(dict.fromkeys(context.missing_information))
        research_blocked = bool(blocking_reasons)

        confidence = context.confidence
        if research_blocked:
            confidence = EligibilityConfidence.LOW

        preferred_characteristics = _clean_list(
            [
                *facts.category_ideal_profiles,
                *facts.strategy_partnership_principles,
            ]
        )
        sponsorship_purpose = _clean_list([facts.needs, facts.goals])
        assumptions = []
        if facts.analyzed_target_audiences and not facts.audience:
            assumptions.append(
                "Audience context uses the existing organization analysis."
            )

        return SponsorEligibilityAnalysis(
            rule_version=self.ruleset.version,
            normalized_facts=facts,
            audience_age_context=context.age_context,
            audience_type=(
                facts.analyzed_target_audiences
                or ([facts.audience] if facts.audience else [])
            ),
            initiative_or_event_type=_infer_initiative_type(facts),
            geographic_focus=facts.location or "Not provided",
            sponsorship_purpose=sponsorship_purpose,
            preferred_sponsor_characteristics=preferred_characteristics,
            excluded_industries=exclusions,
            sensitive_categories=_infer_sensitive_categories(facts),
            age_appropriateness_requirements=list(
                dict.fromkeys(context.age_requirements)
            ),
            brand_safety_requirements=list(
                dict.fromkeys(context.brand_safety_requirements)
            ),
            eligibility_status=(
                EligibilityStatus.BLOCKED
                if research_blocked
                else EligibilityStatus.ELIGIBLE
            ),
            research_blocked=research_blocked,
            blocking_reasons=blocking_reasons,
            confidence=confidence,
            missing_information=missing_information,
            assumptions_used=assumptions,
            applied_rules=audits,
            exclusion_sources=[
                ExclusionSource(
                    industry_code=item.industry_code,
                    rule_id=item.rule_id,
                    reason_code=item.reason_code,
                    source=item.source,
                )
                for item in exclusions
            ],
        )


def generate_sponsor_eligibility_analysis(
    organization: Any,
    initiative: Any,
    analysis: Any,
    strategy: Any,
    categories: Any,
    assets: Any,
    *,
    explicit_restrictions: Iterable[str] = (),
    engine: SponsorEligibilityEngine | None = None,
) -> SponsorEligibilityAnalysis:
    """Normalize current facts and execute the deterministic engine."""

    facts = normalize_eligibility_facts(
        organization,
        initiative,
        analysis,
        strategy,
        categories,
        assets,
        explicit_restrictions=explicit_restrictions,
    )
    return (engine or SponsorEligibilityEngine()).evaluate(facts)

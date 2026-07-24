"""Version-one deterministic sponsor eligibility business rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.sponsor_eligibility import (
    AppliedEligibilityRule,
    AudienceAgeContext,
    EligibilityConfidence,
    EligibilityEvidenceSource,
    EligibilityFacts,
    IndustryExclusion,
)


RULE_VERSION = "sponsor-eligibility-v1"

MINOR_RESTRICTED_INDUSTRIES = (
    ("alcohol", "Alcohol"),
    ("tobacco", "Tobacco"),
    ("vaping", "Vaping"),
    ("cannabis", "Cannabis"),
    ("gambling", "Gambling"),
    ("sports-betting", "Sports Betting"),
    ("adult-entertainment", "Adult Entertainment"),
    ("firearms-weapons", "Firearms and Weapons"),
    ("predatory-financial-products", "Predatory Financial Products"),
    ("other-age-inappropriate", "Other Clearly Age-Inappropriate Industries"),
)

CHILD_PATTERNS = (
    r"\bchild(?:ren)?\b",
    r"\bkids?\b",
    r"\belementary\b",
    r"\bpreschool\b",
    r"\bunder\s+1[0-3]\b",
)
YOUTH_PATTERNS = (
    r"\byouth\b",
    r"\bteens?\b",
    r"\bminors?\b",
    r"\bmiddle school\b",
    r"\bhigh school\b",
    r"\bk-?12\b",
    r"\bunder\s+18\b",
)
MIXED_PATTERNS = (
    r"\bfamil(?:y|ies)\b",
    r"\ball ages\b",
    r"\bmixed[- ]age\b",
    r"\badults? and (?:children|youth|minors?)\b",
)
ADULT_PATTERNS = (
    r"\badults? only\b",
    r"\badults?\s+18\+",
    r"\badults?\s+21\+",
    r"\b18 and older\b",
    r"\b21 and older\b",
    r"\b21\+",
    r"\badult professionals?\b",
)


@dataclass(frozen=True)
class RuleEffect:
    """Deterministic effect and audit record from one rule."""

    audit: AppliedEligibilityRule
    age_context: AudienceAgeContext | None = None
    confidence: EligibilityConfidence | None = None
    exclusions: tuple[IndustryExclusion, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    age_requirements: tuple[str, ...] = ()
    brand_safety_requirements: tuple[str, ...] = ()


@dataclass
class EligibilityRuleContext:
    """Mutable rule context assembled only from deterministic effects."""

    facts: EligibilityFacts
    age_context: AudienceAgeContext = AudienceAgeContext.UNCLEAR
    confidence: EligibilityConfidence = EligibilityConfidence.LOW
    exclusions: list[IndustryExclusion] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    age_requirements: list[str] = field(default_factory=list)
    brand_safety_requirements: list[str] = field(default_factory=list)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _audit(
    rule_id: str,
    reason_code: str,
    outcome: str,
    *sources: EligibilityEvidenceSource,
) -> AppliedEligibilityRule:
    return AppliedEligibilityRule(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        reason_code=reason_code,
        evidence_sources=list(sources),
        outcome=outcome,
    )


class AudienceAgeContextRule:
    """Classify age context from raw audience facts before AI summaries."""

    rule_id = "audience_age_context"

    def evaluate(self, context: EligibilityRuleContext) -> RuleEffect:
        raw_text = context.facts.audience
        supplemental_text = " ".join(context.facts.analyzed_target_audiences)
        combined_text = f"{raw_text} {supplemental_text}".strip()

        has_child = _matches(combined_text, CHILD_PATTERNS)
        has_youth = _matches(combined_text, YOUTH_PATTERNS)
        has_mixed = _matches(combined_text, MIXED_PATTERNS)
        has_adult = _matches(combined_text, ADULT_PATTERNS)

        source = (
            EligibilityEvidenceSource.QUESTIONNAIRE
            if raw_text
            else EligibilityEvidenceSource.ORGANIZATION_ANALYSIS
        )

        if has_mixed or (has_adult and (has_child or has_youth)):
            age_context = AudienceAgeContext.MIXED_WITH_MINORS
            reason = "mixed_audience_contains_minors"
            confidence = EligibilityConfidence.HIGH
        elif has_child:
            age_context = AudienceAgeContext.CHILDREN
            reason = "child_audience_identified"
            confidence = EligibilityConfidence.HIGH
        elif has_youth:
            age_context = AudienceAgeContext.YOUTH
            reason = "youth_audience_identified"
            confidence = EligibilityConfidence.HIGH
        elif has_adult:
            age_context = AudienceAgeContext.ADULT_ONLY
            reason = "adult_only_audience_identified"
            confidence = EligibilityConfidence.HIGH
        else:
            age_context = AudienceAgeContext.UNCLEAR
            reason = "audience_age_context_unclear"
            confidence = EligibilityConfidence.LOW

        return RuleEffect(
            audit=_audit(
                self.rule_id,
                reason,
                f"age_context={age_context.value}",
                source,
            ),
            age_context=age_context,
            confidence=confidence,
        )


class RequiredContextRule:
    """Identify missing factual inputs needed for safe research."""

    rule_id = "required_context"

    def evaluate(self, context: EligibilityRuleContext) -> RuleEffect:
        missing = []
        blocking = []
        if not context.facts.audience:
            missing.append("audience")
            blocking.append("audience_information_required")
        if not context.facts.mission:
            missing.append("mission")
            blocking.append("mission_information_required")
        if not context.facts.location:
            missing.append("geographic_focus")

        outcome = (
            "required_context_complete"
            if not missing
            else "missing=" + ",".join(missing)
        )
        return RuleEffect(
            audit=_audit(
                self.rule_id,
                "required_context_evaluated",
                outcome,
                EligibilityEvidenceSource.QUESTIONNAIRE,
            ),
            blocking_reasons=tuple(blocking),
            missing_information=tuple(missing),
        )


class UnclearAgeResearchBlockRule:
    """Block research unless the audience age context is known."""

    rule_id = "unclear_age_research_block"

    def evaluate(self, context: EligibilityRuleContext) -> RuleEffect:
        if context.age_context is AudienceAgeContext.UNCLEAR:
            return RuleEffect(
                audit=_audit(
                    self.rule_id,
                    "age_context_confirmation_required",
                    "research_blocked",
                    EligibilityEvidenceSource.DETERMINISTIC_RULE,
                ),
                blocking_reasons=("audience_age_context_required",),
                missing_information=("audience_age_context",),
            )

        return RuleEffect(
            audit=_audit(
                self.rule_id,
                "age_context_confirmed",
                "not_applicable",
                EligibilityEvidenceSource.DETERMINISTIC_RULE,
            )
        )


class MinorAudienceIndustryExclusionRule:
    """Apply mandatory age-safety exclusions to audiences with minors."""

    rule_id = "minor_audience_industry_exclusions"

    def evaluate(self, context: EligibilityRuleContext) -> RuleEffect:
        minor_contexts = {
            AudienceAgeContext.CHILDREN,
            AudienceAgeContext.YOUTH,
            AudienceAgeContext.MIXED_WITH_MINORS,
        }
        if context.age_context not in minor_contexts:
            return RuleEffect(
                audit=_audit(
                    self.rule_id,
                    "minor_audience_not_identified",
                    "not_applicable",
                    EligibilityEvidenceSource.DETERMINISTIC_RULE,
                )
            )

        exclusions = tuple(
            IndustryExclusion(
                industry_code=code,
                industry_label=label,
                rule_id=self.rule_id,
                reason_code="minor_audience_age_safety",
                source=EligibilityEvidenceSource.DETERMINISTIC_RULE,
            )
            for code, label in MINOR_RESTRICTED_INDUSTRIES
        )
        return RuleEffect(
            audit=_audit(
                self.rule_id,
                "minor_audience_age_safety",
                f"excluded_industries={len(exclusions)}",
                EligibilityEvidenceSource.QUESTIONNAIRE,
                EligibilityEvidenceSource.DETERMINISTIC_RULE,
            ),
            exclusions=exclusions,
            age_requirements=(
                "All sponsors and activations must be appropriate for minors.",
                "Restricted products must not be marketed, sampled, or promoted.",
            ),
            brand_safety_requirements=(
                "Sponsors must maintain brands appropriate for audiences "
                "that include minors.",
            ),
        )


class ExplicitRestrictionRule:
    """Apply future user restrictions with highest decision authority."""

    rule_id = "explicit_user_restrictions"

    def evaluate(self, context: EligibilityRuleContext) -> RuleEffect:
        restrictions = context.facts.explicit_restrictions
        if not restrictions:
            return RuleEffect(
                audit=_audit(
                    self.rule_id,
                    "no_explicit_restrictions",
                    "not_applicable",
                    EligibilityEvidenceSource.USER_RESTRICTION,
                )
            )

        exclusions = tuple(
            IndustryExclusion(
                industry_code=re.sub(
                    r"[^a-z0-9]+",
                    "-",
                    restriction.lower(),
                ).strip("-"),
                industry_label=restriction,
                rule_id=self.rule_id,
                reason_code="user_provided_restriction",
                source=EligibilityEvidenceSource.USER_RESTRICTION,
            )
            for restriction in restrictions
            if restriction.strip()
        )
        return RuleEffect(
            audit=_audit(
                self.rule_id,
                "user_provided_restriction",
                f"excluded_industries={len(exclusions)}",
                EligibilityEvidenceSource.USER_RESTRICTION,
            ),
            exclusions=exclusions,
        )


class SponsorEligibilityRulesV1:
    """Ordered immutable version-one eligibility ruleset."""

    version = RULE_VERSION
    rules = (
        AudienceAgeContextRule(),
        RequiredContextRule(),
        UnclearAgeResearchBlockRule(),
        MinorAudienceIndustryExclusionRule(),
        ExplicitRestrictionRule(),
    )

    def execute(
        self,
        facts: EligibilityFacts,
    ) -> tuple[EligibilityRuleContext, list[AppliedEligibilityRule]]:
        context = EligibilityRuleContext(facts=facts)
        audits = []

        for rule in self.rules:
            effect = rule.evaluate(context)
            audits.append(effect.audit)
            if effect.age_context is not None:
                context.age_context = effect.age_context
            if effect.confidence is not None:
                context.confidence = effect.confidence
            context.exclusions.extend(effect.exclusions)
            context.blocking_reasons.extend(effect.blocking_reasons)
            context.missing_information.extend(effect.missing_information)
            context.age_requirements.extend(effect.age_requirements)
            context.brand_safety_requirements.extend(
                effect.brand_safety_requirements
            )

        return context, audits

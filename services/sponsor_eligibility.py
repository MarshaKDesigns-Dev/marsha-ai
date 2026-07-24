"""Typed inputs and outputs for deterministic sponsor eligibility decisions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AudienceAgeContext(str, Enum):
    """Supported age contexts used by the eligibility rules."""

    CHILDREN = "children"
    YOUTH = "youth"
    MIXED_WITH_MINORS = "mixed_with_minors"
    ADULT_ONLY = "adult_only"
    UNCLEAR = "unclear"


class EligibilityStatus(str, Enum):
    """Whether future sponsor research may proceed."""

    ELIGIBLE = "eligible"
    BLOCKED = "blocked"


class EligibilityConfidence(str, Enum):
    """Confidence in the normalized eligibility facts."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EligibilityEvidenceSource(str, Enum):
    """Controlled sources available to deterministic rules."""

    QUESTIONNAIRE = "questionnaire"
    ORGANIZATION_ANALYSIS = "organization_analysis"
    SPONSORSHIP_STRATEGY = "sponsorship_strategy"
    SPONSOR_CATEGORY = "sponsor_category"
    SPONSORSHIP_ASSET = "sponsorship_asset"
    USER_RESTRICTION = "user_restriction"
    DETERMINISTIC_RULE = "deterministic_rule"


class EligibilityFacts(BaseModel):
    """Normalized factual input consumed by the eligibility rules."""

    model_config = ConfigDict(frozen=True)

    organization_type: str = ""
    mission: str = ""
    location: str = ""
    initiative_name: str = ""
    audience: str = ""
    needs: str = ""
    goals: str = ""
    fundraising_target: str = ""
    deadline: str = ""

    analyzed_target_audiences: list[str] = Field(default_factory=list)
    analysis_risks_or_gaps: list[str] = Field(default_factory=list)
    strategy_partnership_principles: list[str] = Field(default_factory=list)
    strategy_sponsor_benefits: list[str] = Field(default_factory=list)
    category_slugs: list[str] = Field(default_factory=list)
    category_names: list[str] = Field(default_factory=list)
    category_ideal_profiles: list[str] = Field(default_factory=list)
    asset_names: list[str] = Field(default_factory=list)
    explicit_restrictions: list[str] = Field(default_factory=list)


class AppliedEligibilityRule(BaseModel):
    """Auditable record emitted by every executed rule."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    rule_version: str
    reason_code: str
    evidence_sources: list[EligibilityEvidenceSource]
    outcome: str


class IndustryExclusion(BaseModel):
    """One industry excluded by a specific deterministic rule."""

    model_config = ConfigDict(frozen=True)

    industry_code: str
    industry_label: str
    rule_id: str
    reason_code: str
    source: EligibilityEvidenceSource


class ExclusionSource(BaseModel):
    """Compact audit reference for a finalized industry exclusion."""

    model_config = ConfigDict(frozen=True)

    industry_code: str
    rule_id: str
    reason_code: str
    source: EligibilityEvidenceSource


class SponsorEligibilityAnalysis(BaseModel):
    """Final business-rule decision produced by Marsha AI."""

    model_config = ConfigDict(frozen=True)

    rule_version: str
    normalized_facts: EligibilityFacts
    audience_age_context: AudienceAgeContext
    audience_type: list[str]
    initiative_or_event_type: str
    geographic_focus: str
    sponsorship_purpose: list[str]
    preferred_sponsor_characteristics: list[str]
    excluded_industries: list[IndustryExclusion]
    sensitive_categories: list[str]
    age_appropriateness_requirements: list[str]
    brand_safety_requirements: list[str]
    eligibility_status: EligibilityStatus
    research_blocked: bool
    blocking_reasons: list[str]
    confidence: EligibilityConfidence
    missing_information: list[str]
    assumptions_used: list[str]
    applied_rules: list[AppliedEligibilityRule]
    exclusion_sources: list[ExclusionSource]

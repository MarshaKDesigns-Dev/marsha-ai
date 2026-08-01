

import os, json, smtplib, sys
from email.message import EmailMessage
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from flask import g, jsonify, render_template, request, redirect, url_for, flash, session
from openai import OpenAI
from application import app
from extensions import db
from services.dashboard import build_dashboard
from services.sponsor_eligibility_gate import (
    CategoryResearchDecision,
    evaluate_category_research,
)
from services.sponsor_research_readiness import (
    audience_age_context_is_clear,
    evaluate_sponsor_research_readiness,
    missing_strategy_meeting_answers,
    validate_approval_status,
)
from services.sponsorship_context import (
    GEOGRAPHIC_RADII,
    GEOGRAPHIC_SCOPES,
    SPONSORSHIP_NEEDS,
    dump_list,
    json_list,
    parse_multiline,
    validate_needs,
)
from services.workflow_labels import opportunity_stage_label, workflow_label
from services.workflow_navigation import (
    build_opportunity_progress,
    build_primary_navigation,
)

app.jinja_env.filters["workflow_label"] = workflow_label
app.jinja_env.globals["opportunity_stage_label"] = opportunity_stage_label

if __name__ == "__main__":
    sys.modules.setdefault("app", sys.modules[__name__])

DEFAULT_ORG = {
    "name": "Organization",
    "organization_type": "Organization",
    "location": "",
    "mission": "",
    "sender_name": "",
    "sender_title": "",
    "sender_email": "",
    "website": "",
    "phone": ""
}

CATEGORIES = [
    {"slug": "healthcare", "category": "Healthcare & Wellness", "fit": "Women’s wellness, preventive care, mental wellness, confidence, and community impact.", "score": 90},
    {"slug": "beauty", "category": "Beauty & Personal Care", "fit": "Confidence, preparation, self-expression, and delegate experience.", "score": 95},
    {"slug": "fashion", "category": "Fashion & Size-Inclusive Retail", "fit": "Size-inclusive fashion, styling, wardrobe, and pageant preparation.", "score": 93},
    {"slug": "financial", "category": "Financial Services", "fit": "Financial confidence, entrepreneurship, women’s economic influence, and community education.", "score": 86},
    {"slug": "automotive", "category": "Automotive", "fit": "Local visibility, transportation, event activation, and community sponsorship.", "score": 80},
]


def _phase1_form_context(organization=None, initiative=None):
    return {
        "sponsorship_need_options": SPONSORSHIP_NEEDS,
        "geographic_scope_options": GEOGRAPHIC_SCOPES,
        "geographic_radius_options": GEOGRAPHIC_RADII,
        "selected_sponsorship_needs": set(
            json_list(
                getattr(initiative, "sponsorship_needs_json", "[]")
            )
        ),
        "dream_sponsors_value": "\n".join(
            json_list(getattr(initiative, "dream_sponsors_json", "[]"))
        ),
        "desired_categories_value": "\n".join(
            json_list(
                getattr(
                    initiative,
                    "desired_sponsor_categories_json",
                    "[]",
                )
            )
        ),
        "current_sponsors_value": "\n".join(
            json_list(getattr(organization, "current_sponsors_json", "[]"))
        ),
        "existing_relationships_value": "\n".join(
            json_list(
                getattr(organization, "existing_relationships_json", "[]")
            )
        ),
        "already_contacted_value": "\n".join(
            json_list(
                getattr(
                    organization,
                    "businesses_already_contacted_json",
                    "[]",
                )
            )
        ),
        "never_contact_value": "\n".join(
            json_list(
                getattr(
                    organization,
                    "businesses_never_contact_json",
                    "[]",
                )
            )
        ),
    }


def _apply_phase1_context(organization, initiative):
    selected_needs = validate_needs(
        request.form.getlist("sponsorship_needs")
    )
    initiative.sponsorship_needs_json = dump_list(selected_needs)
    initiative.sponsorship_needs_other = request.form.get(
        "sponsorship_needs_other",
        "",
    ).strip()
    initiative.sponsorship_needs_notes = request.form.get(
        "sponsorship_needs_notes",
        "",
    ).strip()
    initiative.desired_sponsor_categories_json = dump_list(
        parse_multiline(
            request.form.get("desired_sponsor_categories", "")
        )
    )
    scope = request.form.get("geographic_scope", "").strip()
    initiative.geographic_scope = (
        scope if scope in GEOGRAPHIC_SCOPES else None
    )
    radius_value = request.form.get("geographic_radius_miles", "").strip()
    radius = int(radius_value) if radius_value.isdigit() else None
    initiative.geographic_radius_miles = (
        radius
        if initiative.geographic_scope == "Radius"
        and radius in GEOGRAPHIC_RADII
        else None
    )
    initiative.dream_sponsors_json = dump_list(
        parse_multiline(request.form.get("dream_sponsors", ""))
    )
    organization.current_sponsors_json = dump_list(
        parse_multiline(request.form.get("current_sponsors", ""))
    )
    organization.existing_relationships_json = dump_list(
        parse_multiline(request.form.get("existing_relationships", ""))
    )
    organization.businesses_already_contacted_json = dump_list(
        parse_multiline(
            request.form.get("businesses_already_contacted", "")
        )
    )
    organization.businesses_never_contact_json = dump_list(
        parse_multiline(
            request.form.get("businesses_never_contact", "")
        )
    )
    return selected_needs

ASSETS = [
    {"name": "Presenting Partnership", "value": "Top-level association with the initiative", "capacity": "1"},
    {"name": "Category Exclusivity", "value": "Exclusive sponsor position within a business category", "capacity": "Limited"},
    {"name": "Delegate Experience Partner", "value": "Workshops, products, services, or education for delegates", "capacity": "Limited"},
    {"name": "Community Impact Partner", "value": "Visible alignment with service and community initiatives", "capacity": "Limited"},
    {"name": "Program Book Presence", "value": "Print visibility and sponsor storytelling", "capacity": "Multiple"},
    {"name": "Digital Visibility", "value": "Website, social, email, and campaign acknowledgment", "capacity": "Multiple"},
    {"name": "Event Activation", "value": "On-site display, sampling, or engagement", "capacity": "Limited"},
]

STAGES = ["Ready to Send", "Sent", "Follow-Up Due", "Responded", "Meeting", "Proposal", "Won", "Lost"]

TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
TEST_EMAIL = os.getenv("TEST_EMAIL", "")
SENDER_NAME = os.getenv("SENDER_NAME", "Organization Representative")
SENDER_TITLE = os.getenv("SENDER_TITLE", "Organization Representative")
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")


class Organization(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    organization_type = db.Column(db.String(100))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    mission = db.Column(db.Text)
    sender_name = db.Column(db.String(200))
    sender_title = db.Column(db.String(200))
    sender_email = db.Column(db.String(250))
    website = db.Column(db.String(300))
    phone = db.Column(db.String(100))
    current_sponsors_json = db.Column(db.Text, default="[]")
    existing_relationships_json = db.Column(db.Text, default="[]")
    businesses_already_contacted_json = db.Column(db.Text, default="[]")
    businesses_never_contact_json = db.Column(db.Text, default="[]")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    initiatives = db.relationship(
        "SponsorshipInitiative",
        backref="organization",
        lazy=True,
        cascade="all, delete-orphan"
    )

    @property
    def location(self):
        parts = [part for part in [self.city, self.state] if part]
        return ", ".join(parts)


class SponsorshipInitiative(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False
    )
    name = db.Column(db.String(250), nullable=False)
    fundraising_target = db.Column(db.String(200))
    deadline = db.Column(db.Date)
    audience = db.Column(db.Text)
    needs = db.Column(db.Text)
    sponsorship_needs_json = db.Column(db.Text, default="[]")
    sponsorship_needs_other = db.Column(db.Text)
    sponsorship_needs_notes = db.Column(db.Text)
    desired_sponsor_categories_json = db.Column(db.Text, default="[]")
    geographic_scope = db.Column(db.String(50))
    geographic_radius_miles = db.Column(db.Integer)
    dream_sponsors_json = db.Column(db.Text, default="[]")
    goals = db.Column(db.Text)
    sponsorship_goals = db.Column(db.Text)
    estimated_reach = db.Column(db.Text)
    strategy_top_priorities = db.Column(db.Text)
    strategy_priority_sponsors = db.Column(db.Text)
    strategy_success_beyond_fundraising = db.Column(db.Text)
    strategy_concerns_constraints = db.Column(db.Text)
    strategy_meeting_completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(50), default="Active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class SponsorshipIntelligenceJob(db.Model):
    """Durable background job for one intelligence generation attempt."""

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False,
    )
    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
        nullable=False,
    )
    status = db.Column(db.String(20), nullable=False, default="pending")
    regenerate = db.Column(db.Boolean, nullable=False, default=False)
    generation_step = db.Column(db.String(100))
    error_code = db.Column(db.String(100))
    message = db.Column(db.Text)
    failure_details_json = db.Column(db.Text)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    worker_id = db.Column(db.String(255))
    active_key = db.Column(db.String(255), nullable=True, unique=True)
    available_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    lease_expires_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_intelligence_job_status",
        ),
        db.Index(
            "ix_intelligence_job_pending_lookup",
            "status",
            "available_at",
        ),
        db.Index(
            "ix_intelligence_job_initiative_history",
            "organization_id",
            "initiative_id",
            "created_at",
        ),
        db.Index(
            "ix_intelligence_job_lease_recovery",
            "status",
            "lease_expires_at",
        ),
    )

class SponsorshipIntelligence(db.Model):
    """Persisted high-level AI analysis and strategy for an initiative."""

    id = db.Column(db.Integer, primary_key=True)

    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False,
    )

    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
        nullable=False,
        unique=True,
    )

    organization_analysis_json = db.Column(
        db.Text,
        nullable=False,
        default="{}",
    )

    sponsorship_strategy_json = db.Column(
        db.Text,
        nullable=False,
        default="{}",
    )

    sponsor_eligibility_json = db.Column(
        db.Text,
        nullable=True,
    )

    generated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    @property
    def organization_analysis(self):
        """Return the stored organization analysis as a dictionary."""

        try:
            return json.loads(self.organization_analysis_json or "{}")
        except (TypeError, ValueError):
            return {}

    @property
    def sponsorship_strategy(self):
        """Return the stored sponsorship strategy as a dictionary."""

        try:
            return json.loads(self.sponsorship_strategy_json or "{}")
        except (TypeError, ValueError):
            return {}

    @property
    def sponsor_eligibility(self):
        """Return validated deterministic sponsor eligibility, when present."""

        from services.sponsor_eligibility_serialization import (
            SponsorEligibilitySerializationError,
            deserialize_sponsor_eligibility,
        )

        try:
            return deserialize_sponsor_eligibility(
                self.sponsor_eligibility_json
            )
        except SponsorEligibilitySerializationError:
            return None


class ResearchPriority(db.Model):
    """Persisted AI-generated research direction for one sponsor category."""

    id = db.Column(db.Integer, primary_key=True)

    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False,
    )

    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
        nullable=False,
    )

    category_slug = db.Column(
        db.String(100),
        nullable=False,
    )

    priority = db.Column(
        db.Integer,
        nullable=False,
    )

    ideal_sponsor_profile = db.Column(
        db.Text,
        nullable=False,
    )

    research_direction = db.Column(
        db.Text,
        nullable=False,
    )

    qualification_signals_json = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )

    verification_requirements_json = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )

    disqualification_signals_json = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )

    recommended_asset_names_json = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )

    outreach_angle = db.Column(
        db.Text,
        nullable=False,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "initiative_id",
            "category_slug",
            name="uq_research_priority_initiative_category",
        ),
    )

    @staticmethod
    def _load_json_list(value):
        try:
            result = json.loads(value or "[]")
            return result if isinstance(result, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def qualification_signals(self):
        return self._load_json_list(
            self.qualification_signals_json
        )

    @property
    def verification_requirements(self):
        return self._load_json_list(
            self.verification_requirements_json
        )

    @property
    def disqualification_signals(self):
        return self._load_json_list(
            self.disqualification_signals_json
        )

    @property
    def recommended_asset_names(self):
        return self._load_json_list(
            self.recommended_asset_names_json
        )
        

class SponsorCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False
    )
    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
        nullable=False
    )
    slug = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(200), nullable=False)
    fit = db.Column(db.Text)
    score = db.Column(db.Integer, default=0)
    priority = db.Column(db.Integer)
    ideal_sponsor_profile = db.Column(db.Text)
    research_direction = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class SponsorProspect(db.Model):
    """Evidence-backed sponsor prospect for an approved category."""

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False,
    )
    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
        nullable=False,
    )
    sponsorship_asset_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_asset.id"),
    )
    category_slug = db.Column(db.String(100), nullable=False)
    company_key = db.Column(db.String(300), nullable=False)
    company_name = db.Column(db.String(300), nullable=False)
    website = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(300), nullable=False)
    industry = db.Column(db.String(200), nullable=False)
    why_fits = db.Column(db.Text, nullable=False)
    relevant_connection = db.Column(db.Text, nullable=False)
    geographic_relevance = db.Column(db.Text, nullable=False)
    evidence_type = db.Column(db.String(50), nullable=False)
    evidence_json = db.Column(db.Text, nullable=False, default="[]")
    research_date = db.Column(db.Date, nullable=False)
    confidence = db.Column(db.String(20), nullable=False)
    uncertainty_json = db.Column(db.Text, nullable=False, default="[]")
    ranking_score = db.Column(db.Integer, nullable=False)
    ranking_explanation = db.Column(db.Text, nullable=False)
    verified_information_json = db.Column(db.Text, nullable=False, default="[]")
    why_recommended = db.Column(db.Text)
    organization_fit = db.Column(db.Text)
    recommended_ask = db.Column(db.Text)
    contribution_type = db.Column(db.String(50))
    why_may_say_yes = db.Column(db.Text)
    why_may_say_yes_evidence_json = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )
    recommendation_strength = db.Column(db.String(20))
    recommendation_strength_score = db.Column(db.Integer)
    strength_factors_json = db.Column(db.Text, nullable=False, default="{}")
    contact_name = db.Column(db.String(200))
    contact_title = db.Column(db.String(200))
    contact_department = db.Column(db.String(250))
    contact_email = db.Column(db.String(250))
    contact_phone = db.Column(db.String(100))
    contact_url = db.Column(db.Text)
    contact_evidence_url = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "initiative_id",
            "category_slug",
            "company_key",
            name="uq_sponsor_prospect_initiative_category_company",
        ),
        db.Index(
            "ix_sponsor_prospect_category_ranking",
            "organization_id",
            "initiative_id",
            "category_slug",
            "ranking_score",
        ),
    )

    @staticmethod
    def _load_list(value):
        try:
            result = json.loads(value or "[]")
            return result if isinstance(result, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def evidence_sources(self):
        return self._load_list(self.evidence_json)

    @property
    def uncertainty(self):
        return self._load_list(self.uncertainty_json)

    @property
    def verified_information(self):
        return self._load_list(self.verified_information_json)

    @property
    def why_may_say_yes_evidence(self):
        return self._load_list(self.why_may_say_yes_evidence_json)

    @property
    def strength_factors(self):
        try:
            result = json.loads(self.strength_factors_json or "{}")
            return result if isinstance(result, dict) else {}
        except (TypeError, ValueError):
            return {}


class SponsorshipAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False
    )
    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
        nullable=False
    )
    name = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Text)
    capacity = db.Column(db.String(100))
    description = db.Column(db.Text)
    sponsor_value = db.Column(db.Text)
    audience_value = db.Column(db.Text)
    delivery_method = db.Column(db.Text)
    exclusivity = db.Column(db.String(150))
    measurement_method = db.Column(db.Text)
    recommended_categories_json = db.Column(
        db.Text,
        default="[]"
    )
    is_active = db.Column(db.Boolean, default=True)
    approval_status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending",
    )
    approval_updated_at = db.Column(db.DateTime)
    source = db.Column(
        db.String(20),
        nullable=False,
        default="generated",
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.CheckConstraint(
            "approval_status IN ('Pending', 'Approved', 'Rejected')",
            name="ck_sponsorship_asset_approval_status",
        ),
    )

    @property
    def recommended_categories(self):
        """Return the recommended sponsor-category slugs."""

        try:
            result = json.loads(
                self.recommended_categories_json or "[]"
            )
            return result if isinstance(result, list) else []
        except (TypeError, ValueError):
            return []


class ResearchAssignment(db.Model):
    """One durable Research Worker run for one approved asset."""

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
        nullable=False,
    )
    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
        nullable=False,
    )
    sponsorship_asset_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_asset.id"),
        nullable=False,
    )
    status = db.Column(db.String(30), nullable=False, default="ready")
    active_key = db.Column(db.String(255), nullable=True, unique=True)
    worker_id = db.Column(db.String(255))
    lease_expires_at = db.Column(db.DateTime)
    available_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    result_count = db.Column(db.Integer, nullable=False, default=0)
    results_json = db.Column(db.Text, nullable=False, default="[]")
    error_details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('ready', 'working', 'completed', 'needs_attention')",
            name="ck_research_assignment_status",
        ),
        db.Index(
            "ix_research_assignment_scope",
            "organization_id",
            "initiative_id",
            "sponsorship_asset_id",
            "created_at",
        ),
        db.Index(
            "ix_research_assignment_claim",
            "status",
            "available_at",
            "lease_expires_at",
        ),
    )

    @property
    def results(self):
        try:
            result = json.loads(self.results_json or "[]")
            return result if isinstance(result, list) else []
        except (TypeError, ValueError):
            return []


class SponsorResearchDiagnostic(db.Model):
    """Safe attempt-level audit metadata for Sponsor Research."""

    id = db.Column(db.Integer, primary_key=True)
    research_assignment_id = db.Column(
        db.Integer, db.ForeignKey("research_assignment.id"), nullable=False
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organization.id"), nullable=False
    )
    initiative_id = db.Column(
        db.Integer, db.ForeignKey("sponsorship_initiative.id"), nullable=False
    )
    sponsorship_asset_id = db.Column(
        db.Integer, db.ForeignKey("sponsorship_asset.id"), nullable=False
    )
    provider_response_id = db.Column(db.String(255))
    outcome_code = db.Column(db.String(100))
    search_queries_json = db.Column(db.Text, nullable=False, default="[]")
    source_urls_json = db.Column(db.Text, nullable=False, default="[]")
    candidate_count = db.Column(db.Integer, nullable=False, default=0)
    accepted_count = db.Column(db.Integer, nullable=False, default=0)
    rejected_count = db.Column(db.Integer, nullable=False, default=0)
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index(
            "ix_sponsor_research_diagnostic_assignment_history",
            "research_assignment_id",
            "created_at",
        ),
    )


class SponsorResearchCandidateDiagnostic(db.Model):
    """Safe per-candidate Sponsor Research validation decisions."""

    id = db.Column(db.Integer, primary_key=True)
    diagnostic_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsor_research_diagnostic.id"),
        nullable=False,
    )
    candidate_name = db.Column(db.String(300), nullable=False)
    canonical_website = db.Column(db.Text)
    industry = db.Column(db.String(200))
    result_status = db.Column(db.String(20), nullable=False)
    rejection_codes_json = db.Column(db.Text, nullable=False, default="[]")
    citation_validation_json = db.Column(db.Text, nullable=False, default="{}")
    eligibility_result_json = db.Column(db.Text, nullable=False, default="{}")
    preference_result_json = db.Column(db.Text, nullable=False, default="{}")
    approved_asset_match = db.Column(db.Boolean)
    approved_need_match = db.Column(db.Boolean)
    deduplication_result = db.Column(db.String(30), nullable=False)
    evidence_urls_json = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.CheckConstraint(
            "result_status IN ('accepted', 'rejected')",
            name="ck_sponsor_research_candidate_diagnostic_status",
        ),
        db.Index(
            "ix_sponsor_research_candidate_diagnostic_history",
            "diagnostic_id",
            "result_status",
        ),
    )


class ResearchAssignmentSelection(db.Model):
    """Persisted link between one reviewed result and its Pipeline record."""

    id = db.Column(db.Integer, primary_key=True)
    research_assignment_id = db.Column(
        db.Integer, db.ForeignKey("research_assignment.id"), nullable=False
    )
    sponsor_prospect_id = db.Column(
        db.Integer, db.ForeignKey("sponsor_prospect.id"), nullable=False
    )
    opportunity_id = db.Column(
        db.Integer, db.ForeignKey("opportunity.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "research_assignment_id", "sponsor_prospect_id",
            name="uq_research_assignment_selection_assignment_prospect",
        ),
        db.Index(
            "ix_research_assignment_selection_assignment_history",
            "research_assignment_id", "created_at",
        ),
        db.Index(
            "ix_research_assignment_selection_prospect",
            "sponsor_prospect_id",
        ),
    )


class ResearchRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prospect_key = db.Column(db.String(250), unique=True, nullable=False)
    parent_prospect = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    score = db.Column(db.Integer)

    recommended_target = db.Column(db.String(200))
    contact_name = db.Column(db.String(200))
    title = db.Column(db.String(200))
    department = db.Column(db.String(250))
    email = db.Column(db.String(250))
    phone = db.Column(db.String(100))
    contact_url = db.Column(db.Text)
    linkedin_url = db.Column(db.Text)
    why_this_contact = db.Column(db.Text)
    confidence = db.Column(db.String(100))
    verified_date = db.Column(db.String(50))
    sources_json = db.Column(db.Text, default="[]")

    outreach = db.Column(db.Text)
    outreach_channel = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def sources(self):
        try:
            return json.loads(self.sources_json or "[]")
        except Exception:
            return []

class Opportunity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization.id"),
    )
    initiative_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_initiative.id"),
    )
    sponsorship_asset_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsorship_asset.id"),
    )
    sponsor_prospect_id = db.Column(
        db.Integer,
        db.ForeignKey("sponsor_prospect.id"),
    )
    parent_prospect = db.Column(db.String(200), nullable=False)
    recommended_target = db.Column(db.String(200))
    category = db.Column(db.String(100))
    score = db.Column(db.Integer)

    contact_name = db.Column(db.String(200))
    title = db.Column(db.String(200))
    department = db.Column(db.String(250))
    email = db.Column(db.String(250))
    phone = db.Column(db.String(100))
    contact_url = db.Column(db.Text)
    linkedin_url = db.Column(db.Text)

    why_this_contact = db.Column(db.Text)
    confidence = db.Column(db.String(100))
    verified_date = db.Column(db.String(50))
    sources_json = db.Column(db.Text, default="[]")

    outreach = db.Column(db.Text)
    outreach_channel = db.Column(db.String(50))

    stage = db.Column(db.String(50), default="Ready to Send")
    sent_date = db.Column(db.Date)
    follow_up_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    subject = db.Column(db.String(300))
    delivery_recipient = db.Column(db.String(250))
    delivery_mode = db.Column(db.String(50))

    reviewed_message = db.Column(db.Text)
    message_review_notes = db.Column(db.Text)
    message_reviewed_at = db.Column(db.DateTime)
    message_approved_at = db.Column(db.DateTime)

    follow_up_subject = db.Column(db.String(300))
    follow_up_message = db.Column(db.Text)
    follow_up_review_notes = db.Column(db.Text)
    follow_up_reviewed_at = db.Column(db.DateTime)
    follow_up_completed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    contact_research_jobs = db.relationship(
        "ContactResearchJob",
        back_populates="opportunity",
        order_by="ContactResearchJob.created_at",
    )

    @property
    def sources(self):
        try:
            return json.loads(self.sources_json or "[]")
        except Exception:
            return []


class ContactResearchJob(db.Model):
    """Durable Contact Discovery lifecycle for one Opportunity."""

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(
        db.Integer,
        db.ForeignKey("opportunity.id"),
        nullable=False,
    )
    status = db.Column(db.String(20), nullable=False, default="queued")
    error_message = db.Column(db.Text)
    result_json = db.Column(db.Text)
    provider_response_id = db.Column(db.String(255))
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    opportunity = db.relationship("Opportunity", back_populates="contact_research_jobs")
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_contact_research_job_status",
        ),
        db.Index("ix_contact_research_job_opportunity_created", "opportunity_id", "created_at"),
    )


class OutreachGenerationJob(db.Model):
    """Durable Outreach Worker generation attempt for one Opportunity."""

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id"), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False)
    initiative_id = db.Column(db.Integer, db.ForeignKey("sponsorship_initiative.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="queued")
    active_key = db.Column(db.String(255), nullable=True, unique=True)
    worker_id = db.Column(db.String(255))
    lease_expires_at = db.Column(db.DateTime)
    available_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    provider_response_id = db.Column(db.String(255))
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('queued', 'working', 'completed', 'failed')",
            name="ck_outreach_generation_job_status",
        ),
        db.Index("ix_outreach_generation_claim", "status", "available_at", "lease_expires_at"),
        db.Index("ix_outreach_generation_history", "opportunity_id", "created_at"),
    )


class FollowUpGenerationJob(db.Model):
    """Durable Follow-Up Worker generation attempt for one Opportunity."""

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id"), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False)
    initiative_id = db.Column(db.Integer, db.ForeignKey("sponsorship_initiative.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="queued")
    active_key = db.Column(db.String(255), nullable=True, unique=True)
    worker_id = db.Column(db.String(255))
    lease_expires_at = db.Column(db.DateTime)
    available_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    provider_response_id = db.Column(db.String(255))
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)
    __table_args__ = (
        db.CheckConstraint("status IN ('queued', 'working', 'completed', 'failed')", name="ck_follow_up_generation_job_status"),
        db.Index("ix_follow_up_generation_claim", "status", "available_at", "lease_expires_at"),
        db.Index("ix_follow_up_generation_history", "opportunity_id", "created_at"),
    )


def get_active_organization():
    organization_id = session.get("organization_id")

    if organization_id:
        organization = db.session.get(Organization, organization_id)
        if organization:
            return organization

    organization = Organization.query.filter_by(is_active=True).first()

    if not organization:
        organization = Organization.query.first()

    if organization:
        session["organization_id"] = organization.id

    return organization


def get_active_initiative():
    organization = get_active_organization()
    initiative_id = session.get("initiative_id")

    if initiative_id:
        initiative = db.session.get(SponsorshipInitiative, initiative_id)
        if initiative and (
            not organization or initiative.organization_id == organization.id
        ):
            return initiative

    if not organization:
        return None

    initiative = SponsorshipInitiative.query.filter_by(
        organization_id=organization.id,
        status="Active"
    ).order_by(SponsorshipInitiative.updated_at.desc()).first()

    if not initiative:
        initiative = SponsorshipInitiative.query.filter_by(
            organization_id=organization.id
        ).order_by(SponsorshipInitiative.updated_at.desc()).first()

    if initiative:
        session["initiative_id"] = initiative.id

    return initiative


@app.context_processor
def inject_customer_brand():
    """Expose one consistent customer brand to the shared layout."""

    organization = get_active_organization()
    initiative = get_active_initiative()
    intelligence = (
        get_sponsorship_intelligence(organization, initiative)
        if organization and initiative
        else None
    )
    assets = (
        get_sponsorship_assets(organization, initiative)
        if intelligence is not None
        else []
    )
    opportunities = getattr(g, "workflow_opportunities", None)
    if opportunities is None:
        opportunities = (
            Opportunity.query.filter_by(
                organization_id=organization.id,
                initiative_id=initiative.id,
            ).all()
            if organization and initiative
            else []
        )
    return {
        "brand_organization": organization,
        "workflow_navigation": build_primary_navigation(
            organization=organization,
            initiative=initiative,
            intelligence=intelligence,
            assets=assets,
            opportunities=opportunities,
        ),
    }


def get_org_profile():
    organization = get_active_organization()

    if not organization:
        return DEFAULT_ORG.copy()

    return {
        "name": organization.name,
        "organization_type": organization.organization_type or "",
        "location": organization.location or DEFAULT_ORG["location"],
        "mission": organization.mission or DEFAULT_ORG["mission"],
        "sender_name": organization.sender_name or SENDER_NAME,
        "sender_title": organization.sender_title or SENDER_TITLE,
        "sender_email": organization.sender_email or SMTP_EMAIL,
        "website": organization.website or "",
        "phone": organization.phone or ""
    }


def get_initiative_profile():
    initiative = get_active_initiative()

    if not initiative:
        return {
            "initiative": "",
            "target": "",
            "deadline": "",
            "audience": "",
            "needs": "",
            "goals": "",
            "sponsorship_goals": "",
            "estimated_reach": "",
        }

    return {
        "initiative": initiative.name,
        "target": initiative.fundraising_target or "",
        "deadline": initiative.deadline.isoformat() if initiative.deadline else "",
        "audience": initiative.audience or "",
        "needs": initiative.needs or "",
        "goals": initiative.goals or "",
        "sponsorship_goals": initiative.sponsorship_goals or "",
        "estimated_reach": initiative.estimated_reach or "",
    }


def get_sender_name():
    return get_org_profile().get("sender_name") or SENDER_NAME


def get_sender_title():
    return get_org_profile().get("sender_title") or SENDER_TITLE



def get_worker_context():
    organization = get_org_profile()
    initiative = get_initiative_profile()

    return {
        "organization_name": organization.get("name") or "Organization",
        "organization_type": organization.get("organization_type") or "Organization",
        "location": organization.get("location") or "",
        "mission": organization.get("mission") or "",
        "sender_name": organization.get("sender_name") or get_sender_name(),
        "sender_title": organization.get("sender_title") or get_sender_title(),
        "sender_email": organization.get("sender_email") or "",
        "website": organization.get("website") or "",
        "organization_phone": organization.get("phone") or "",
        "initiative_name": initiative.get("initiative") or "",
        "fundraising_target": initiative.get("target") or "",
        "deadline": initiative.get("deadline") or "",
        "audience": initiative.get("audience") or "",
        "needs": initiative.get("needs") or "",
        "goals": initiative.get("goals") or ""
    }


def seed_sponsorship_intelligence(organization, initiative):
    category_count = SponsorCategory.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id
    ).count()

    if category_count == 0:
        for category in CATEGORIES:
            db.session.add(
                SponsorCategory(
                    organization_id=organization.id,
                    initiative_id=initiative.id,
                    slug=category["slug"],
                    category=category["category"],
                    fit=category["fit"],
                    score=category["score"],
                    is_active=True
                )
            )

    asset_count = SponsorshipAsset.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id
    ).count()

    if asset_count == 0:
        for asset in ASSETS:
            db.session.add(
                SponsorshipAsset(
                    organization_id=organization.id,
                    initiative_id=initiative.id,
                    name=asset["name"],
                    value=asset["value"],
                    capacity=asset["capacity"],
                    is_active=True
                )
            )

    db.session.commit()


def get_sponsor_categories(organization, initiative):
    return SponsorCategory.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        is_active=True
    ).order_by(SponsorCategory.score.desc()).all()


def get_sponsorship_assets(organization, initiative):
    return SponsorshipAsset.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        is_active=True
    ).order_by(SponsorshipAsset.id.asc()).all()


def get_sponsorship_intelligence(organization, initiative):
    return SponsorshipIntelligence.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id
    ).first()


def get_research_priorities(organization, initiative):
    return ResearchPriority.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        is_active=True
    ).order_by(ResearchPriority.priority.asc()).all()


def get_category_research_decision(
    category_slug,
    *,
    require_research_readiness=True,
):
    """Return the persisted deterministic gate for one active category."""

    organization = get_active_organization()
    initiative = get_active_initiative()

    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        return CategoryResearchDecision(
            allowed=False,
            reason=(
                "Complete organization and sponsorship initiative setup "
                "before category research."
            ),
            reason_code="workspace_setup_required",
        )

    category = SponsorCategory.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        slug=category_slug,
        is_active=True,
    ).first()
    if category is None:
        return CategoryResearchDecision(
            allowed=False,
            reason=(
                "This sponsor category is not available for the active "
                "initiative."
            ),
            reason_code="category_not_available",
        )

    intelligence = get_sponsorship_intelligence(
        organization,
        initiative,
    )
    eligibility = (
        getattr(intelligence, "sponsor_eligibility", None)
        if intelligence is not None
        else None
    )
    eligibility_decision = evaluate_category_research(
        eligibility,
        category,
    )
    if not eligibility_decision.allowed:
        return eligibility_decision
    if not require_research_readiness:
        return eligibility_decision

    readiness = evaluate_sponsor_research_readiness(
        initiative,
        get_sponsorship_assets(organization, initiative),
        intelligence=intelligence,
    )
    return CategoryResearchDecision(
        allowed=readiness.allowed,
        reason=readiness.reason,
        reason_code=readiness.reason_code,
    )


def get_active_sponsor_category(category_slug):
    """Return one category belonging to the active workspace."""

    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        return None
    return SponsorCategory.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        slug=category_slug,
        is_active=True,
    ).first()


def sponsor_prospect_context(prospect_record, category_record):
    """Adapt a persisted prospect to existing downstream worker inputs."""

    return {
        "name": prospect_record.company_name,
        "location": prospect_record.location,
        "category": category_record.category,
        "score": prospect_record.ranking_score,
        "fit": prospect_record.why_fits,
        "angle": prospect_record.relevant_connection,
    }


def run_workspace_intelligence_generation(
    organization_id,
    initiative_id,
    *,
    regenerate=False,
    workflow_budget_seconds=None,
):
    """Call the workspace application service without a circular import."""

    from services.generate_sponsorship_intelligence import (
        generate_workspace_intelligence,
    )

    options = {
        "regenerate": regenerate,
    }
    if workflow_budget_seconds is not None:
        options["workflow_budget_seconds"] = workflow_budget_seconds
    return generate_workspace_intelligence(
        organization_id,
        initiative_id,
        **options,
    )


def enqueue_workspace_intelligence_generation(
    organization,
    initiative,
    *,
    regenerate=False,
):
    """Create or reuse one durable background generation job."""

    from services.sponsorship_intelligence_jobs import enqueue_job

    return enqueue_job(
        organization,
        initiative,
        regenerate=regenerate,
    )


def get_workspace_intelligence_job(organization, initiative):
    """Return the active job, or the latest historical job when inactive."""

    from services.sponsorship_intelligence_jobs import (
        get_active_job,
        get_latest_job,
    )

    active_job = get_active_job(organization.id, initiative.id)
    if active_job is not None:
        return active_job
    return get_latest_job(organization.id, initiative.id)


def client():
    key = os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=key) if key else None



def draft_outreach(prospect, contact, *, worker_context=None):
    c = client()

    if not c:
        return "OPENAI_API_KEY is not configured. Outreach could not be drafted."

    context = worker_context or get_worker_context()

    prompt = f"""
You are the Outreach Drafting Worker for Marsha AI's Sponsorship Coordinator.

Turn verified contact research into clear, recipient-facing sponsorship outreach.

Organization:
Name: {context['organization_name']}
Type: {context['organization_type']}
Location: {context['location']}
Mission: {context['mission']}
Website: {context['website']}

Active sponsorship initiative:
Name: {context['initiative_name']}
Fundraising target: {context['fundraising_target']}
Deadline: {context['deadline']}
Audience: {context['audience']}
Needs: {context['needs']}
Goals: {context['goals']}

Sender:
Name: {context['sender_name']}
Title: {context['sender_title']}
Email: {context['sender_email']}

Prospect:
Name: {prospect['name']}
Category: {prospect['category']}
Fit: {prospect['fit']}
Recommended sponsorship angle: {prospect['angle']}

Verified contact research:
Recommended target: {contact.get('recommended_target')}
Contact name: {contact.get('contact_name')}
Title: {contact.get('title')}
Department: {contact.get('department')}
Email: {contact.get('email')}
Phone: {contact.get('phone')}
Contact form URL: {contact.get('contact_url')}
Why this contact: {contact.get('why_this_contact')}

Rules:
- Write only the outreach content.
- Use the saved organization and initiative information; do not assume a pageant,
  nonprofit, event, or campaign type that was not provided.
- Do not expose research notes, source language, or internal routing labels.
- If no named person is verified, use a natural role-based greeting.
- If an email is available, write a concise email.
- If there is no email but a phone number is available, write a short call script.
- If there is no email or phone number but a contact form URL is available,
  write a concise contact-form message.
- For contact-form messages, do not include an email subject line.
- Connect the request to the prospect using only verified or supplied facts.
- Do not invent audience size, event attendance, benefits, relationships,
  sponsorship inventory, or commitments.
- Do not overpromise sponsor outcomes.
- Make the next step specific and easy to answer.
- Keep the tone professional, direct, and human.
- End with the saved sender name, sender title, and organization name.
"""

    try:
        response = c.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        return response.output_text.strip()
    except Exception as e:
        return f"Outreach drafting failed: {str(e)}"



def draft_follow_up(opp, *, worker_context=None):
    c = client()

    if not c:
        return {"error": "OPENAI_API_KEY is not configured."}

    context = worker_context or get_worker_context()
    channel = opp.outreach_channel or "email"
    original_message = opp.reviewed_message or opp.outreach or ""

    prompt = f"""
You are the Follow-Up Worker for Marsha AI's Sponsorship Coordinator.

Create a concise first follow-up for sponsorship outreach that has not received
a recorded response.

Organization:
Name: {context['organization_name']}
Type: {context['organization_type']}
Location: {context['location']}
Mission: {context['mission']}

Active sponsorship initiative:
Name: {context['initiative_name']}
Fundraising target: {context['fundraising_target']}
Deadline: {context['deadline']}
Audience: {context['audience']}
Needs: {context['needs']}
Goals: {context['goals']}

Sender:
Name: {context['sender_name']}
Title: {context['sender_title']}
Email: {context['sender_email']}

Opportunity:
Parent prospect: {opp.parent_prospect}
Recommended target: {opp.recommended_target}
Decision-maker: {opp.contact_name}
Title: {opp.title}
Department: {opp.department}
Channel: {channel}
Original outreach date: {opp.sent_date}
Reason this contact was selected: {opp.why_this_contact}

Original outreach:
{original_message}

Rules:
- Use the saved organization and active initiative context.
- Do not invent a prospect response.
- Do not imply the original outreach was read.
- Do not repeat the entire original pitch.
- Keep the follow-up brief, respectful, and specific.
- Mention the earlier outreach naturally.
- Include one clear next step.
- Avoid pressure, urgency, guilt, or unsupported claims.
- For email, return a subject and message.
- For phone, return a natural follow-up call script and use an empty subject.
- For contact_form, return a concise follow-up message and use an empty subject.
- Return only JSON with keys: subject, message.
"""

    try:
        response = c.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        text = response.output_text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        result = json.loads(text)

        return {
            "subject": result.get("subject") or "",
            "message": result.get("message") or ""
        }
    except Exception as e:
        return {"error": f"Follow-up drafting failed: {str(e)}"}



def review_follow_up_quality(opp, subject, message):
    c = client()

    if not c:
        return {"error": "OPENAI_API_KEY is not configured."}

    context = get_worker_context()
    channel = opp.outreach_channel or "email"

    prompt = f"""
You are the Message Quality Review Worker for Marsha AI's Sponsorship Coordinator.

Review and improve a sponsorship follow-up before the user sends, calls, or
submits it.

Organization:
Name: {context['organization_name']}
Type: {context['organization_type']}
Location: {context['location']}
Mission: {context['mission']}

Active sponsorship initiative:
Name: {context['initiative_name']}
Fundraising target: {context['fundraising_target']}
Deadline: {context['deadline']}
Audience: {context['audience']}
Needs: {context['needs']}
Goals: {context['goals']}

Opportunity:
Parent prospect: {opp.parent_prospect}
Recommended target: {opp.recommended_target}
Decision-maker: {opp.contact_name}
Title: {opp.title}
Department: {opp.department}
Channel: {channel}
Original outreach date: {opp.sent_date}
Follow-up due date: {opp.follow_up_date}

Current follow-up subject:
{subject}

Current follow-up:
{message}

Rules:
- Preserve the saved organization and initiative facts.
- Do not invent facts, benefits, results, relationships, or a prospect response.
- Do not claim the original outreach was read.
- Do not overpromise sponsor outcomes.
- Keep the follow-up brief, respectful, specific, and easy to answer.
- Remove pressure, guilt, unsupported urgency, and repetitive language.
- Include one clear next step.
- For phone, make the script natural when spoken aloud.
- For contact forms, keep the message compact.
- For phone and contact_form, improved_subject must be an empty string.
- Return only JSON with keys:
improved_subject, improved_message, review_notes, risk_flags.
- risk_flags must be a list.
"""

    try:
        response = c.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        text = response.output_text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        return json.loads(text)
    except Exception as e:
        return {"error": f"Follow-up quality review failed: {str(e)}"}


def determine_outreach_channel(contact):
    if contact.get("email"):
        return "email"

    if contact.get("phone"):
        return "phone"

    if contact.get("contact_url"):
        return "contact_form"

    return "unknown"


def opportunity_has_usable_contact(opportunity):
    """Return whether an Opportunity has an existing delivery route."""

    return any(
        (
            getattr(opportunity, "email", None),
            getattr(opportunity, "phone", None),
            getattr(opportunity, "contact_url", None),
        )
    )


def opportunity_can_generate_outreach(opportunity):
    """Return whether existing Outreach Worker generation may begin."""

    return bool(
        getattr(opportunity, "stage", None) == "Research Approved"
        and opportunity_has_usable_contact(opportunity)
        and not getattr(opportunity, "outreach", None)
        and not getattr(opportunity, "reviewed_message", None)
    )


def review_message_quality(opp, subject, message):
    c = client()

    if not c:
        return {"error": "OPENAI_API_KEY is not configured."}

    context = get_worker_context()
    channel = opp.outreach_channel or "email"

    channel_instructions = {
        "phone": (
            "Improve a sponsorship phone call script. Make it natural when "
            "spoken aloud. improved_subject must be an empty string."
        ),
        "contact_form": (
            "Improve a sponsorship contact-form message. Keep it concise enough "
            "for a typical web form. improved_subject must be an empty string."
        ),
        "email": (
            "Improve a sponsorship outreach email, including its subject line."
        )
    }

    prompt = f"""
You are the Message Quality Review Worker for Marsha AI's Sponsorship Coordinator.

{channel_instructions.get(channel, channel_instructions['email'])}

Organization:
Name: {context['organization_name']}
Type: {context['organization_type']}
Location: {context['location']}
Mission: {context['mission']}
Website: {context['website']}

Active sponsorship initiative:
Name: {context['initiative_name']}
Fundraising target: {context['fundraising_target']}
Deadline: {context['deadline']}
Audience: {context['audience']}
Needs: {context['needs']}
Goals: {context['goals']}

Sender:
Name: {context['sender_name']}
Title: {context['sender_title']}
Email: {context['sender_email']}

Opportunity:
Parent prospect: {opp.parent_prospect}
Recommended target: {opp.recommended_target}
Decision-maker: {opp.contact_name}
Title: {opp.title}
Department: {opp.department}
Category: {opp.category}
Channel: {channel}
Email: {opp.email}
Phone: {opp.phone}
Contact form URL: {opp.contact_url}
Reason this contact was selected: {opp.why_this_contact}

Current subject:
{subject}

Current outreach:
{message}

Rules:
- Preserve the supplied organization, initiative, sender, prospect, and contact facts.
- Treat the sender name, title, and email as immutable facts.
- Use the sender title exactly as provided: "{context['sender_title']}".
- Never shorten, promote, replace, or substitute the sender title.
- If the current outreach contains a conflicting sender title, replace it with
  the exact saved sender title above.
- Do not assume the organization is a pageant, nonprofit, event, or other type
  unless that information appears above.
- Do not invent audience size, attendance, sponsor benefits, inventory,
  relationships, results, commitments, or contact details.
- Do not claim an existing relationship unless stated.
- Do not overpromise sponsorship outcomes.
- Make the parent organization and recommended target clear when relevant.
- Keep the message concise, respectful, specific, professional, and human.
- Include one clear next step.
- Correct awkward phrasing and remove internal research language.
- Return only JSON with keys:
improved_subject, improved_message, review_notes, risk_flags.
- risk_flags must be a list.
"""

    try:
        response = c.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        text = response.output_text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        return json.loads(text)
    except Exception as e:
        return {"error": f"Outreach Review failed: {str(e)}"}


@app.route("/setup", methods=["GET", "POST"])
def setup():
    organization = get_active_organization()
    initiative = get_active_initiative()

    if request.method == "POST":
        organization_name = request.form.get("organization_name", "").strip()
        initiative_name = request.form.get("initiative_name", "").strip()

        if not organization_name or not initiative_name:
            flash(
                "Organization name and sponsorship initiative name are required.",
                "warning"
            )
            return render_template(
                "setup.html",
                organization=organization,
                initiative=initiative,
                **_phase1_form_context(organization, initiative),
            )

        if not organization:
            organization = Organization()
            db.session.add(organization)

        organization.name = organization_name
        organization.organization_type = request.form.get(
            "organization_type",
            ""
        ).strip()
        organization.city = request.form.get("city", "").strip()
        organization.state = request.form.get("state", "").strip()
        organization.mission = request.form.get("mission", "").strip()
        organization.sender_name = request.form.get(
            "sender_name",
            ""
        ).strip()
        organization.sender_title = request.form.get(
            "sender_title",
            ""
        ).strip()
        organization.sender_email = request.form.get(
            "sender_email",
            ""
        ).strip()
        organization.website = request.form.get("website", "").strip()
        organization.phone = request.form.get("phone", "").strip()
        organization.is_active = True

        db.session.flush()
        session["organization_id"] = organization.id

        if not initiative:
            initiative = SponsorshipInitiative(
                organization_id=organization.id
            )
            db.session.add(initiative)

        initiative.organization_id = organization.id
        initiative.name = initiative_name
        initiative.fundraising_target = request.form.get(
            "fundraising_target",
            ""
        ).strip()

        deadline_value = request.form.get("deadline", "").strip()
        initiative.deadline = (
            datetime.strptime(deadline_value, "%Y-%m-%d").date()
            if deadline_value
            else None
        )

        initiative.audience = request.form.get("audience", "").strip()
        initiative.needs = request.form.get("needs", "").strip()
        initiative.goals = request.form.get("goals", "").strip()
        initiative.status = "Active"
        _apply_phase1_context(organization, initiative)

        db.session.commit()

        session["initiative_id"] = initiative.id
        session["initiative"] = get_initiative_profile()

        flash(
            "Organization and sponsorship initiative saved.",
            "success"
        )
        return redirect(url_for("workspace"))

    return render_template(
        "setup.html",
        organization=organization,
        initiative=initiative,
        **_phase1_form_context(organization, initiative),
    )


@app.route("/")
def home():
    organization = get_active_organization()
    initiative = get_active_initiative()

    return render_template(
        "home.html",
        organization=organization,
        initiative=initiative,
        opportunity_count=Opportunity.query.count()
    )


@app.route("/start", methods=["GET", "POST"])
def start():
    if request.method == "POST":
        session["initiative"] = {
            "initiative": request.form["initiative"],
            "target": request.form["target"],
            "deadline": request.form["deadline"],
            "audience": request.form["audience"],
            "needs": request.form["needs"]
        }
        return redirect(url_for("workspace"))

    return render_template("start.html", org=get_org_profile())


@app.route("/workspace")
def workspace():
    organization = get_active_organization()
    initiative = get_active_initiative()

    if not organization or not initiative:
        flash(
            "Complete organization and sponsorship initiative setup first.",
            "warning"
        )
        return redirect(url_for("setup"))

    session["initiative"] = get_initiative_profile()
    intelligence = get_sponsorship_intelligence(
        organization,
        initiative,
    )
    generation_job = get_workspace_intelligence_job(
        organization,
        initiative,
    )
    categories = (
        get_sponsor_categories(organization, initiative)
        if intelligence
        else []
    )
    top_category = categories[0] if categories else None
    assets = (
        get_sponsorship_assets(organization, initiative)
        if intelligence
        else []
    )
    prospects = SponsorProspect.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        is_active=True,
    ).order_by(
        SponsorProspect.updated_at.desc(),
        SponsorProspect.id.desc(),
    ).all()
    research_assignments = ResearchAssignment.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
    ).order_by(
        ResearchAssignment.created_at.desc(),
        ResearchAssignment.id.desc(),
    ).all()
    asset_names = {asset.id: asset.name for asset in assets}
    for assignment in research_assignments:
        assignment.asset_name = asset_names.get(
            assignment.sponsorship_asset_id
        )
    opportunities = Opportunity.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
    ).order_by(
        Opportunity.updated_at.desc()
    ).all()
    from services.outreach_generation_jobs import get_latest_job as latest_outreach_job
    from services.follow_up_generation_jobs import get_latest_job as latest_follow_up_job
    for opportunity in opportunities:
        opportunity.outreach_generation_job = latest_outreach_job(opportunity.id)
        opportunity.follow_up_generation_job = latest_follow_up_job(opportunity.id)
        contact_jobs = getattr(opportunity, "contact_research_jobs", ()) or ()
        opportunity.contact_research_job = (
            contact_jobs[-1] if contact_jobs else None
        )
    g.workflow_opportunities = opportunities
    dashboard = build_dashboard(
        organization=organization,
        initiative=initiative,
        intelligence=intelligence,
        generation_job=generation_job,
        top_category=top_category,
        assets=assets,
        prospects=prospects,
        opportunities=opportunities,
        research_assignments=research_assignments,
    )

    return render_template(
        "workspace.html",
        organization=organization,
        initiative=initiative,
        dashboard=dashboard,
    )


@app.route("/workspace/status")
def workspace_status():
    """Return the active intelligence-job state for dashboard polling."""

    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        return jsonify(
            {
                "status": "setup_required",
                "terminal": True,
                "refresh_url": url_for("setup"),
            }
        )

    job = get_workspace_intelligence_job(organization, initiative)
    status = (
        (getattr(job, "status", "") or "").lower()
        if job is not None
        else "not_started"
    )
    response = {
        "status": status,
        "terminal": status not in {"pending", "processing"},
        "refresh_url": url_for("workspace"),
    }
    if status == "failed":
        response["message"] = (
            getattr(job, "message", None)
            or "Strategy generation needs attention."
        )
    return jsonify(response)


@app.route("/strategy-meeting", methods=["GET", "POST"])
def strategy_meeting():
    """Collect the operating context required by the Strategy Worker."""

    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash(
            "Complete organization and sponsorship initiative setup first.",
            "warning",
        )
        return redirect(url_for("setup"))

    if request.method == "POST":
        fields = {
            "strategy_top_priorities": request.form.get(
                "strategy_top_priorities",
                "",
            ).strip(),
            "strategy_priority_sponsors": request.form.get(
                "strategy_priority_sponsors",
                "",
            ).strip(),
            "strategy_success_beyond_fundraising": request.form.get(
                "strategy_success_beyond_fundraising",
                "",
            ).strip(),
            "strategy_concerns_constraints": request.form.get(
                "strategy_concerns_constraints",
                "",
            ).strip(),
        }
        missing = missing_strategy_meeting_answers(answers=fields)

        if missing:
            flash(
                "Complete the Sponsorship Strategy fields: "
                + ", ".join(missing)
                + ".",
                "warning",
            )
            return render_template(
                "strategy_meeting.html",
                organization=organization,
                initiative=initiative,
                form_values=fields,
            )

        for name, value in fields.items():
            setattr(initiative, name, value)
        initiative.strategy_meeting_completed_at = (
            datetime.now(UTC).replace(tzinfo=None)
        )
        db.session.commit()

        existing_intelligence = get_sponsorship_intelligence(
            organization,
            initiative,
        )
        if existing_intelligence is not None:
            flash(
                "Strategy inputs updated. Your current strategy has not changed.",
                "success",
            )
            return redirect(url_for("workspace"))

        _, created = enqueue_workspace_intelligence_generation(
            organization,
            initiative,
        )
        flash(
            (
                "Sponsorship Strategy saved. Your Strategy Worker has started."
                if created
                else "Strategy generation is already in progress."
            ),
            "success" if created else "warning",
        )
        return redirect(url_for("workspace"))

    return render_template(
        "strategy_meeting.html",
        organization=organization,
        initiative=initiative,
        form_values=None,
        intelligence=get_sponsorship_intelligence(organization, initiative),
    )


@app.route("/workspace/strategy")
def strategy_work():
    """Render generated strategy work for the active initiative."""

    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash(
            "Complete organization and sponsorship initiative setup first.",
            "warning",
        )
        return redirect(url_for("setup"))

    intelligence = get_sponsorship_intelligence(organization, initiative)
    if intelligence is None:
        flash(
            "Complete Sponsorship Strategy before reviewing strategy work.",
            "warning",
        )
        return redirect(url_for("strategy_meeting"))

    assets = get_sponsorship_assets(organization, initiative)
    return render_template(
        "strategy_work.html",
        organization=organization,
        initiative=initiative,
        intelligence=intelligence,
        strategy=intelligence.sponsorship_strategy,
        categories=get_sponsor_categories(organization, initiative),
        assets=assets,
        strategy_approved=any(
            getattr(asset, "is_active", True)
            and getattr(asset, "approval_status", "Pending") == "Approved"
            for asset in assets
        ),
    )


@app.route("/workspace/strategy/approve", methods=["POST"])
def approve_strategy_work():
    """Approve the generated strategy by approving its recommended assets."""

    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash(
            "Complete organization and sponsorship initiative setup first.",
            "warning",
        )
        return redirect(url_for("setup"))

    intelligence = get_sponsorship_intelligence(organization, initiative)
    if intelligence is None:
        flash("There is no generated strategy to approve.", "warning")
        return redirect(url_for("strategy_meeting"))

    assets = get_sponsorship_assets(organization, initiative)
    if not assets:
        flash(
            "The generated strategy has no sponsorship assets to approve.",
            "warning",
        )
        return redirect(url_for("strategy_work"))

    approved_at = datetime.now(UTC).replace(tzinfo=None)
    for asset in assets:
        if asset.approval_status == "Pending":
            asset.approval_status = "Approved"
            asset.approval_updated_at = approved_at
    db.session.commit()
    flash(
        "Strategy approved. Choose the first sponsorship asset to research.",
        "success",
    )
    return redirect(url_for("research_worker"))


def _active_sponsorship_asset(asset_id):
    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        return None
    return SponsorshipAsset.query.filter_by(
        id=asset_id,
        organization_id=organization.id,
        initiative_id=initiative.id,
        is_active=True,
    ).first()


@app.route("/workspace/assets")
def sponsorship_asset_review():
    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash(
            "Complete organization and sponsorship initiative setup first.",
            "warning",
        )
        return redirect(url_for("setup"))

    intelligence = get_sponsorship_intelligence(
        organization,
        initiative,
    )
    if intelligence is None:
        flash(
            "Complete Sponsorship Strategy before reviewing sponsorship assets.",
            "warning",
        )
        return redirect(url_for("strategy_meeting"))

    assets = get_sponsorship_assets(organization, initiative)
    approved_asset_count = sum(
        getattr(asset, "is_active", True)
        and getattr(asset, "approval_status", "Pending") == "Approved"
        for asset in assets
    )
    return render_template(
        "sponsorship_assets_review.html",
        organization=organization,
        initiative=initiative,
        assets=assets,
        approved_asset_count=approved_asset_count,
    )


@app.route("/workspace/assets/<int:asset_id>", methods=["POST"])
def update_sponsorship_asset(asset_id):
    asset = _active_sponsorship_asset(asset_id)
    if asset is None:
        flash("That sponsorship asset is not available.", "warning")
        return redirect(url_for("sponsorship_asset_review"))

    action = request.form.get("action", "").strip().lower()
    if action in {"approve", "reject"}:
        requested_status = {
            "approve": "Approved",
            "reject": "Rejected",
        }[action]
        asset.approval_status = validate_approval_status(requested_status)
        asset.approval_updated_at = datetime.now(UTC).replace(tzinfo=None)
    elif action == "edit":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        sponsor_value = request.form.get("sponsor_value", "").strip()
        capacity = request.form.get("capacity", "").strip()
        if not name or not sponsor_value:
            flash(
                "Asset name and sponsor value are required.",
                "warning",
            )
            return redirect(url_for("sponsorship_asset_review"))
        asset.name = name
        asset.description = description
        asset.sponsor_value = sponsor_value
        asset.value = sponsor_value
        asset.capacity = capacity
    else:
        flash("Unsupported sponsorship asset action.", "warning")
        return redirect(url_for("sponsorship_asset_review"))

    db.session.commit()
    flash("Sponsorship asset updated.", "success")
    return redirect(url_for("sponsorship_asset_review"))


@app.route("/workspace/assets", methods=["POST"])
def add_sponsorship_asset():
    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash(
            "Complete organization and sponsorship initiative setup first.",
            "warning",
        )
        return redirect(url_for("setup"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    sponsor_value = request.form.get("sponsor_value", "").strip()
    capacity = request.form.get("capacity", "").strip()
    if not name or not sponsor_value:
        flash("Asset name and sponsor value are required.", "warning")
        return redirect(url_for("sponsorship_asset_review"))

    db.session.add(
        SponsorshipAsset(
            organization_id=organization.id,
            initiative_id=initiative.id,
            name=name,
            description=description,
            sponsor_value=sponsor_value,
            value=sponsor_value,
            capacity=capacity,
            approval_status="Pending",
            source="custom",
            is_active=True,
        )
    )
    db.session.commit()
    flash("Custom sponsorship asset added for review.", "success")
    return redirect(url_for("sponsorship_asset_review"))


@app.route("/workspace/generate-intelligence", methods=["POST"])
def generate_workspace_sponsorship_intelligence():
    organization = get_active_organization()
    initiative = get_active_initiative()

    if not organization or not initiative:
        flash(
            "Complete organization and sponsorship initiative setup first.",
            "warning",
        )
        return redirect(url_for("setup"))

    if initiative.organization_id != organization.id:
        flash(
            "The sponsorship initiative does not belong to the organization.",
            "warning",
        )
        return redirect(url_for("workspace"))

    regenerate = request.form.get("regenerate") == "true"
    _, created = enqueue_workspace_intelligence_generation(
        organization,
        initiative,
        regenerate=regenerate,
    )

    if created:
        flash(
            (
                "Your Strategy Worker is rebuilding the sponsorship strategy. "
                "You can continue using the Dashboard while it works."
                if regenerate
                else "Your Strategy Worker has started. You can leave this page "
                "while the strategy is prepared."
            ),
            "success",
        )
    else:
        flash(
            (
                "Strategy regeneration is already in progress."
                if regenerate
                else "Strategy generation is already in progress."
            ),
            "warning",
        )
    return redirect(url_for("workspace"))


def _approved_research_asset(organization, initiative, asset_id):
    return SponsorshipAsset.query.filter_by(
        id=asset_id,
        organization_id=organization.id,
        initiative_id=initiative.id,
        is_active=True,
        approval_status="Approved",
    ).first()


def _research_assignment_context(organization, initiative):
    assets = SponsorshipAsset.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        is_active=True,
        approval_status="Approved",
    ).order_by(SponsorshipAsset.created_at.asc()).all()
    assignments = ResearchAssignment.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
    ).order_by(ResearchAssignment.created_at.desc()).all()
    latest_by_asset = {}
    for assignment in assignments:
        latest_by_asset.setdefault(
            assignment.sponsorship_asset_id,
            assignment,
        )
    saved_counts = {}
    for opportunity in Opportunity.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
    ).all():
        asset_id = opportunity.sponsorship_asset_id
        if asset_id is not None:
            saved_counts[asset_id] = saved_counts.get(asset_id, 0) + 1
    return assets, latest_by_asset, saved_counts, assignments


@app.route("/research")
def research_worker():
    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash("Complete organization and initiative setup first.", "warning")
        return redirect(url_for("setup"))
    assets, latest_by_asset, saved_counts, assignments = _research_assignment_context(
        organization,
        initiative,
    )
    return render_template(
        "research_worker.html",
        assets=assets,
        latest_by_asset=latest_by_asset,
        saved_counts=saved_counts,
        assignment_history=assignments,
        assignment_asset_names={asset.id: asset.name for asset in assets},
    )


@app.route("/research/assets/<int:asset_id>", methods=["POST"])
def start_asset_research(asset_id):
    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash("Complete organization and initiative setup first.", "warning")
        return redirect(url_for("setup"))
    asset = _approved_research_asset(organization, initiative, asset_id)
    if asset is None:
        flash(
            "Select an approved sponsorship asset for this initiative.",
            "warning",
        )
        return redirect(url_for("research_worker"))

    from services.research_assignments import enqueue_assignment

    assignment, created = enqueue_assignment(
        organization,
        initiative,
        asset,
    )
    flash(
        (
            "Your Research Worker has started researching this sponsorship "
            "opportunity."
            if created
            else "Your Research Worker is already researching this "
            "sponsorship opportunity."
        ),
        "success" if created else "warning",
    )
    return redirect(
        url_for("research_assignment", assignment_id=assignment.id)
    )


@app.route("/research/assignments/<int:assignment_id>")
def research_assignment(assignment_id):
    from services.sponsor_prospect_persistence import normalized_company_key

    organization = get_active_organization()
    initiative = get_active_initiative()
    assignment = ResearchAssignment.query.filter_by(
        id=assignment_id,
        organization_id=getattr(organization, "id", None),
        initiative_id=getattr(initiative, "id", None),
    ).first_or_404()
    asset = _approved_research_asset(
        organization,
        initiative,
        assignment.sponsorship_asset_id,
    )
    if asset is None:
        flash(
            "The sponsorship asset for this assignment is no longer approved.",
            "warning",
        )
        return redirect(url_for("research_worker"))
    selection_prospect_ids = {
        row.sponsor_prospect_id
        for row in ResearchAssignmentSelection.query.filter_by(
            research_assignment_id=assignment.id
        ).all()
    }
    prospects_by_key = {
        prospect.company_key: prospect
        for prospect in SponsorProspect.query.filter_by(
            organization_id=organization.id,
            initiative_id=initiative.id,
            is_active=True,
        ).all()
    }
    opportunities_by_prospect = {
        opportunity.sponsor_prospect_id: opportunity
        for opportunity in Opportunity.query.filter_by(
            organization_id=organization.id,
            initiative_id=initiative.id,
        ).all()
        if opportunity.sponsor_prospect_id is not None
    }
    saved_results = {}
    for index, result in enumerate(assignment.results):
        key = normalized_company_key(
            result.get("company_name", ""), result.get("website", "")
        )
        prospect = prospects_by_key.get(key)
        opportunity = (
            opportunities_by_prospect.get(prospect.id) if prospect else None
        )
        if opportunity is not None:
            saved_results[index] = {
                "status": (
                    "saved_from_assignment"
                    if prospect.id in selection_prospect_ids
                    else "already_in_pipeline"
                ),
                "opportunity_id": opportunity.id,
            }
    return render_template(
        "research_results.html",
        assignment=assignment,
        asset=asset,
        results=assignment.results,
        saved_results=saved_results,
    )


@app.route("/research/assignments/<int:assignment_id>/status")
def research_assignment_status(assignment_id):
    organization = get_active_organization()
    initiative = get_active_initiative()
    assignment = ResearchAssignment.query.filter_by(
        id=assignment_id,
        organization_id=getattr(organization, "id", None),
        initiative_id=getattr(initiative, "id", None),
    ).first_or_404()
    return jsonify(
        {
            "status": assignment.status,
            "terminal": assignment.status in {"completed", "needs_attention"},
            "refresh_url": url_for(
                "research_assignment", assignment_id=assignment.id
            ),
        }
    )


@app.route(
    "/research/assignments/<int:assignment_id>/review",
    methods=["POST"],
)
def review_research_assignment(assignment_id):
    from services.research_selection_persistence import (
        ResearchSelectionPersistenceError,
        save_research_selections,
    )
    from services.sponsor_prospect_persistence import SponsorProspectPersistenceError
    from services.sponsor_research import SponsorProspectCandidate

    organization = get_active_organization()
    initiative = get_active_initiative()
    assignment = ResearchAssignment.query.filter_by(
        id=assignment_id,
        organization_id=getattr(organization, "id", None),
        initiative_id=getattr(initiative, "id", None),
        status="completed",
    ).first_or_404()
    asset = _approved_research_asset(
        organization,
        initiative,
        assignment.sponsorship_asset_id,
    )
    if asset is None:
        flash(
            "The sponsorship asset for this assignment is no longer approved.",
            "warning",
        )
        return redirect(url_for("research_worker"))
    action = request.form.get("action")
    if action == "reject_all":
        flash("Results left unchanged. No sponsors were saved.", "success")
        return redirect(
            url_for("research_assignment", assignment_id=assignment.id)
        )

    raw_results = assignment.results
    if action == "save_all":
        selected_indexes = list(range(len(raw_results)))
    else:
        selected_indexes = sorted(
            {
                int(value)
                for value in request.form.getlist("selected_results")
                if value.isdigit() and int(value) < len(raw_results)
            }
        )
    if not selected_indexes:
        flash("Select at least one result to save.", "warning")
        return redirect(
            url_for("research_assignment", assignment_id=assignment.id)
        )

    category = type(
        "AssetCategory",
        (),
        {
            "organization_id": organization.id,
            "initiative_id": initiative.id,
            "slug": f"asset-{asset.id}",
        },
    )()
    try:
        candidates = [
            SponsorProspectCandidate.model_validate(raw_results[index])
            for index in selected_indexes
        ]
        result = save_research_selections(
            organization,
            initiative,
            assignment,
            asset,
            category,
            candidates,
        )
    except (
        ResearchSelectionPersistenceError,
        SponsorProspectPersistenceError,
        ValueError,
    ):
        db.session.rollback()
        flash(
            "The selected results could not be saved. Existing Sponsor Pipeline "
            "records were preserved.",
            "warning",
        )
        return redirect(
            url_for("research_assignment", assignment_id=assignment.id)
        )

    if result.added_count:
        message = (
            f"{result.added_count} sponsor organization"
            f"{'' if result.added_count == 1 else 's'} saved to the "
            "Sponsor Pipeline."
        )
        if result.already_saved_count:
            message += f" {result.already_saved_count} were already saved."
    else:
        message = (
            "No new sponsors were added. "
            f"{result.already_saved_count} selected sponsor"
            f"{' was' if result.already_saved_count == 1 else 's were'} "
            "already saved."
        )
    flash(message, "success")
    return redirect(
        url_for("show_pipeline", new_sponsors=result.added_count)
    )


@app.route("/prospects/<category>", methods=["GET", "POST"])
def prospects(category):
    decision = get_category_research_decision(
        category,
        require_research_readiness=request.method == "POST",
    )
    if not decision.allowed:
        flash(decision.reason, "warning")
        return redirect(url_for("workspace"))

    organization = get_active_organization()
    initiative = get_active_initiative()
    category_record = get_active_sponsor_category(category)
    intelligence = get_sponsorship_intelligence(
        organization,
        initiative,
    )

    if request.method == "POST":
        from services.sponsor_prospect_persistence import (
            SponsorProspectPersistenceError,
            persist_sponsor_prospects,
        )
        from services.sponsor_research import (
            NoCredibleProspectsError,
            SponsorResearchError,
            SponsorResearchUnavailableError,
            research_sponsor_category,
        )

        research_started_at = monotonic()
        app.logger.info(
            (
                "sponsor_research_started organization_id=%s "
                "initiative_id=%s category_slug=%s"
            ),
            organization.id,
            initiative.id,
            category,
        )
        try:
            candidates = research_sponsor_category(
                organization,
                initiative,
                category_record,
                get_sponsorship_assets(organization, initiative),
                intelligence.sponsor_eligibility,
            )
            saved_prospects = persist_sponsor_prospects(
                organization,
                initiative,
                category_record,
                candidates,
            )
            app.logger.info(
                (
                    "sponsor_research_completed organization_id=%s "
                    "initiative_id=%s category_slug=%s prospect_count=%s "
                    "elapsed_seconds=%.3f"
                ),
                organization.id,
                initiative.id,
                category,
                len(saved_prospects),
                monotonic() - research_started_at,
            )
            flash(
                (
                    f"Evidence-backed sponsor research completed. "
                    f"{len(saved_prospects)} sponsor organization"
                    f"{'' if len(saved_prospects) == 1 else 's'} saved."
                ),
                "success",
            )
        except NoCredibleProspectsError as exc:
            app.logger.warning(
                (
                    "sponsor_research_no_results organization_id=%s "
                    "initiative_id=%s category_slug=%s reason_code=%s "
                    "elapsed_seconds=%.3f"
                ),
                organization.id,
                initiative.id,
                category,
                getattr(exc, "reason_code", "no_credible_prospects"),
                monotonic() - research_started_at,
            )
            flash(str(exc), "warning")
        except SponsorResearchUnavailableError as exc:
            app.logger.warning(
                (
                    "sponsor_research_unavailable organization_id=%s "
                    "initiative_id=%s category_slug=%s "
                    "error_code=%s "
                    "elapsed_seconds=%.3f"
                ),
                organization.id,
                initiative.id,
                category,
                getattr(
                    exc,
                    "reason_code",
                    "research_service_unavailable",
                ),
                monotonic() - research_started_at,
            )
            flash(str(exc), "warning")
        except SponsorResearchError as exc:
            app.logger.exception(
                (
                    "sponsor_research_invalid_result organization_id=%s "
                    "initiative_id=%s category_slug=%s "
                    "error_code=invalid_research_result "
                    "elapsed_seconds=%.3f"
                ),
                organization.id,
                initiative.id,
                category,
                monotonic() - research_started_at,
            )
            flash(
                (
                    "Sponsor research returned an invalid result. No new "
                    "sponsors were saved, and existing sponsors were "
                    "preserved."
                ),
                "warning",
            )
        except SponsorProspectPersistenceError:
            app.logger.warning(
                (
                    "sponsor_research_persistence_failed organization_id=%s "
                    "initiative_id=%s category_slug=%s "
                    "error_code=prospect_persistence_failed "
                    "elapsed_seconds=%.3f"
                ),
                organization.id,
                initiative.id,
                category,
                monotonic() - research_started_at,
            )
            flash(
                (
                    "Sponsor Research completed, but the sponsors could not "
                    "be saved. Existing sponsors were preserved."
                ),
                "warning",
            )

    researched_prospects = SponsorProspect.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
        category_slug=category,
        is_active=True,
    ).order_by(
        SponsorProspect.ranking_score.desc(),
        SponsorProspect.company_name.asc(),
    ).all()

    return render_template(
        "prospects.html",
        category=category,
        category_record=category_record,
        prospects=researched_prospects,
    )


@app.route("/prospect/<category>/<int:index>", methods=["GET", "POST"])
def prospect(category, index):
    decision = get_category_research_decision(
        category,
        require_research_readiness=False,
    )
    if not decision.allowed:
        flash(decision.reason, "warning")
        return redirect(url_for("workspace"))

    organization = get_active_organization()
    initiative = get_active_initiative()
    category_record = get_active_sponsor_category(category)
    prospect_record = SponsorProspect.query.filter_by(
        id=index,
        organization_id=organization.id,
        initiative_id=initiative.id,
        category_slug=category,
        is_active=True,
    ).first()
    if prospect_record is None:
        flash("That researched sponsor is not available.", "warning")
        return redirect(url_for("prospects", category=category))

    p = sponsor_prospect_context(prospect_record, category_record)

    existing_opportunity = Opportunity.query.filter_by(
        parent_prospect=p["name"]
    ).first()

    if existing_opportunity:
        return redirect(
            url_for(
                "opportunity_detail",
                opportunity_id=existing_opportunity.id
            )
        )

    prospect_key = f"sponsor_prospect:{prospect_record.id}"

    research_record = ResearchRecord.query.filter_by(
        prospect_key=prospect_key
    ).first()

    contact = {
        "recommended_target": prospect_record.company_name,
        "contact_name": prospect_record.contact_name,
        "title": prospect_record.contact_title,
        "department": prospect_record.contact_department,
        "email": prospect_record.contact_email,
        "phone": prospect_record.contact_phone,
        "contact_url": prospect_record.contact_url,
        "linkedin_url": None,
        "why_this_contact": (
            "Public business contact information found during sponsor research."
            if prospect_record.contact_evidence_url
            else "No reliable public contact was found."
        ),
        "confidence": prospect_record.confidence,
        "verified_date": prospect_record.research_date.isoformat(),
        "sources": prospect_record.evidence_sources,
    }
    outreach = None

    if research_record:
        contact = {
            "recommended_target": research_record.recommended_target,
            "contact_name": research_record.contact_name,
            "title": research_record.title,
            "department": research_record.department,
            "email": research_record.email,
            "phone": research_record.phone,
            "contact_url": research_record.contact_url,
            "linkedin_url": research_record.linkedin_url,
            "why_this_contact": research_record.why_this_contact,
            "confidence": research_record.confidence,
            "verified_date": research_record.verified_date,
            "sources": research_record.sources
        }

        outreach = research_record.outreach

    if request.method == "POST":
        if not any(
            (
                contact.get("email"),
                contact.get("phone"),
                contact.get("contact_url"),
            )
        ):
            flash(
                "No reliable public contact route is available for this "
                "sponsor.",
                "warning",
            )
        else:
            outreach = draft_outreach(p, contact)

            if not research_record:
                research_record = ResearchRecord(
                    prospect_key=prospect_key,
                    parent_prospect=p["name"],
                    category=p["category"],
                    score=p["score"]
                )

                db.session.add(research_record)

            research_record.recommended_target = (
                contact.get("recommended_target") or p["name"]
            )
            research_record.contact_name = contact.get("contact_name")
            research_record.title = contact.get("title")
            research_record.department = contact.get("department")
            research_record.email = contact.get("email")
            research_record.phone = contact.get("phone")
            research_record.contact_url = contact.get("contact_url")
            research_record.linkedin_url = contact.get("linkedin_url")
            research_record.why_this_contact = contact.get("why_this_contact")
            research_record.confidence = contact.get("confidence")
            research_record.verified_date = contact.get("verified_date")
            research_record.sources_json = json.dumps(
                contact.get("sources") or []
            )
            research_record.outreach = outreach

            db.session.commit()

            flash(
                "Contact research completed and saved. Review the evidence before approving.",
                "success"
            )

    return render_template(
        "prospect.html",
        p=p,
        category=category,
        index=index,
        prospect_record=prospect_record,
        contact=contact,
        outreach=outreach
    )
def validate_outreach_readiness(contact, outreach):
    errors = []

    has_email = bool(contact.get("email"))
    has_phone = bool(contact.get("phone"))
    has_contact_url = bool(contact.get("contact_url"))

    if not has_email and not has_phone and not has_contact_url:
        errors.append("No usable delivery route was found.")

    if not outreach or not outreach.strip():
        errors.append("No outreach message was generated.")

    if outreach and "[Director Name]" in outreach:
        errors.append("The outreach message still contains [Director Name].")

    if outreach and "Primary:" in outreach:
        errors.append("Internal research labels are appearing in the outreach message.")

    if not contact.get("sources"):
        errors.append("No research sources were saved.")

    return errors

@app.route("/approve/<category>/<int:index>", methods=["POST"])
def approve(category, index):
    decision = get_category_research_decision(
        category,
        require_research_readiness=False,
    )
    if not decision.allowed:
        flash(decision.reason, "warning")
        return redirect(url_for("workspace"))

    organization = get_active_organization()
    initiative = get_active_initiative()
    category_record = get_active_sponsor_category(category)
    prospect_record = SponsorProspect.query.filter_by(
        id=index,
        organization_id=organization.id,
        initiative_id=initiative.id,
        category_slug=category,
        is_active=True,
    ).first()
    if prospect_record is None:
        flash("That researched sponsor is not available.", "warning")
        return redirect(url_for("prospects", category=category))

    p = sponsor_prospect_context(prospect_record, category_record)
    prospect_key = f"sponsor_prospect:{prospect_record.id}"

    research_record = ResearchRecord.query.filter_by(
        prospect_key=prospect_key
    ).first()

    raw = request.form.get("contact_json")
    outreach = request.form.get("outreach")

    if research_record:
        contact = {
            "recommended_target": research_record.recommended_target,
            "contact_name": research_record.contact_name,
            "title": research_record.title,
            "department": research_record.department,
            "email": research_record.email,
            "phone": research_record.phone,
            "contact_url": research_record.contact_url,
            "linkedin_url": research_record.linkedin_url,
            "why_this_contact": research_record.why_this_contact,
            "confidence": research_record.confidence,
            "verified_date": research_record.verified_date,
            "sources": research_record.sources
        }
        outreach = research_record.outreach

    elif raw:
        contact = json.loads(raw)

    else:
        flash("Contact research must be completed before approval.", "warning")
        return redirect(url_for("prospect", category=category, index=index))
    
    readiness_errors = validate_outreach_readiness(contact, outreach)

    if readiness_errors:
        for error in readiness_errors:
            flash(error, "warning")

        flash("This Sponsor Opportunity is not ready to approve yet.", "warning")
        return redirect(url_for("prospect", category=category, index=index))

    existing = Opportunity.query.filter_by(
        parent_prospect=p["name"],
        contact_name=contact.get("contact_name")
    ).first()

    if existing:
        flash("This Sponsor Opportunity is already saved.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=existing.id))

    opp = Opportunity(
        parent_prospect=p["name"],
        recommended_target=contact.get("recommended_target") or p["name"],
        category=p["category"],
        score=p["score"],
        contact_name=contact.get("contact_name"),
        title=contact.get("title"),
        department=contact.get("department"),
        email=contact.get("email"),
        phone=contact.get("phone"),
        contact_url=contact.get("contact_url"),
        linkedin_url=contact.get("linkedin_url"),
        why_this_contact=contact.get("why_this_contact"),
        confidence=contact.get("confidence"),
        verified_date=contact.get("verified_date"),
        sources_json=json.dumps(contact.get("sources") or []),
        outreach=outreach,
        outreach_channel=determine_outreach_channel(contact),
        stage="Ready to Send"
    )

    db.session.add(opp)
    db.session.commit()

    flash(f"{opp.recommended_target} saved as a Sponsor Opportunity.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/pipeline")
def show_pipeline():
    organization = get_active_organization()
    initiative = get_active_initiative()
    if (
        organization is None
        or initiative is None
        or initiative.organization_id != organization.id
    ):
        flash("Complete organization and initiative setup first.", "warning")
        return redirect(url_for("setup"))

    opportunities = Opportunity.query.filter_by(
        organization_id=organization.id,
        initiative_id=initiative.id,
    ).order_by(Opportunity.updated_at.desc()).all()
    from services.outreach_generation_jobs import get_latest_job as latest_outreach_job
    from services.follow_up_generation_jobs import get_latest_job as latest_follow_up_job
    for opportunity in opportunities:
        opportunity.outreach_generation_job = latest_outreach_job(opportunity.id)
        opportunity.follow_up_generation_job = latest_follow_up_job(opportunity.id)
    g.workflow_opportunities = opportunities

    return render_template(
        "pipeline.html",
        opportunities=opportunities,
        today=date.today(),
    )


@app.route("/opportunity/<int:opportunity_id>")
def opportunity_detail(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)
    contact_research_job = ContactResearchJob.query.filter_by(
        opportunity_id=opp.id,
    ).order_by(
        ContactResearchJob.created_at.desc(),
        ContactResearchJob.id.desc(),
    ).first()
    from services.outreach_generation_jobs import get_latest_job
    outreach_generation_job = get_latest_job(opp.id)
    from services.follow_up_generation_jobs import get_latest_job as latest_follow_up_job
    follow_up_generation_job = latest_follow_up_job(opp.id)

    default_subject = opp.subject or f"Potential partnership with {get_org_profile()['name']}"
    display_message = (opp.reviewed_message or opp.outreach or "").replace(
        "[Director Name]",
        get_sender_name()
    )

    review_notes = None
    if opp.message_review_notes:
        try:
            review_notes = json.loads(opp.message_review_notes)
        except Exception:
            review_notes = None

    follow_up_due = bool(
        opp.stage == "Sent"
        and opp.follow_up_date
        and opp.follow_up_date <= date.today()
    )

    follow_up_review_notes = None
    if opp.follow_up_review_notes:
        try:
            follow_up_review_notes = json.loads(opp.follow_up_review_notes)
        except Exception:
            follow_up_review_notes = None

    return render_template(
        "opportunity.html",
        opp=opp,
        opportunity_progress=build_opportunity_progress(opp),
        stages=STAGES,
        test_mode=TEST_MODE,
        test_email=TEST_EMAIL,
        default_subject=default_subject,
        display_message=display_message,
        contact_research_job=contact_research_job,
        outreach_generation_job=outreach_generation_job,
        follow_up_generation_job=follow_up_generation_job,
        review_notes=review_notes,
        follow_up_due=follow_up_due,
        follow_up_review_notes=follow_up_review_notes
    )


@app.route(
    "/opportunity/<int:opportunity_id>/generate-outreach",
    methods=["POST"],
)
def generate_opportunity_outreach(opportunity_id):
    """Generate the existing Outreach Worker draft for one approved sponsor."""

    organization = get_active_organization()
    initiative = get_active_initiative()
    opportunity = Opportunity.query.filter_by(
        id=opportunity_id,
        organization_id=getattr(organization, "id", None),
        initiative_id=getattr(initiative, "id", None),
    ).first_or_404()

    if getattr(opportunity, "outreach", None):
        return redirect(
            url_for("opportunity_detail", opportunity_id=opportunity.id)
        )
    if not opportunity_can_generate_outreach(opportunity):
        flash(
            "This opportunity needs approved research and a verified contact "
            "route before outreach can be generated.",
            "warning",
        )
        return redirect(
            url_for("opportunity_detail", opportunity_id=opportunity.id)
        )

    from services.outreach_generation_jobs import enqueue_job
    _, created = enqueue_job(organization, initiative, opportunity)
    flash(
        (
            "Your Outreach Worker has started preparing the sponsor message."
            if created else
            "Your Outreach Worker is already preparing this message."
        ),
        "success" if created else "warning",
    )
    return redirect(
        url_for("opportunity_detail", opportunity_id=opportunity.id)
    )


@app.route("/opportunity/<int:opportunity_id>/outreach-status")
def outreach_generation_status(opportunity_id):
    organization = get_active_organization(); initiative = get_active_initiative()
    opportunity = Opportunity.query.filter_by(
        id=opportunity_id, organization_id=getattr(organization, "id", None),
        initiative_id=getattr(initiative, "id", None),
    ).first_or_404()
    from services.outreach_generation_jobs import get_latest_job
    job = get_latest_job(opportunity.id)
    status = getattr(job, "status", "not_started")
    return jsonify({"status": status, "terminal": status in {"completed", "failed"},
                    "refresh_url": url_for("opportunity_detail", opportunity_id=opportunity.id)})


@app.route(
    "/opportunity/<int:opportunity_id>/research-contact",
    methods=["POST"],
)
def enqueue_contact_research(opportunity_id):
    organization = get_active_organization()
    initiative = get_active_initiative()
    opportunity = Opportunity.query.filter_by(
        id=opportunity_id,
        organization_id=getattr(organization, "id", None),
        initiative_id=getattr(initiative, "id", None),
    ).first_or_404()

    active_job = ContactResearchJob.query.filter_by(
        opportunity_id=opportunity.id,
    ).filter(
        ContactResearchJob.status.in_(("queued", "processing")),
    ).order_by(
        ContactResearchJob.created_at.desc(),
        ContactResearchJob.id.desc(),
    ).first()
    if active_job is None:
        db.session.add(
            ContactResearchJob(
                opportunity_id=opportunity.id,
                status="queued",
            )
        )
        db.session.commit()

    return redirect(
        url_for("opportunity_detail", opportunity_id=opportunity.id)
    )


@app.route("/opportunity/<int:opportunity_id>/review-message", methods=["POST"])
def review_message(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    channel = opp.outreach_channel or "email"

    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if channel == "email" and (not subject or not message):
        flash("Subject and outreach are required before review.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    if channel != "email" and not message:
        flash("Call script is required before review.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    result = review_message_quality(opp, subject, message)

    if result.get("error"):
        flash(result["error"], "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    opp.subject = result.get("improved_subject") or subject
    opp.reviewed_message = result.get("improved_message") or message
    opp.outreach = opp.reviewed_message
    opp.message_review_notes = json.dumps({
        "review_notes": result.get("review_notes"),
        "risk_flags": result.get("risk_flags") or []
    })
    opp.message_reviewed_at = datetime.utcnow()
    opp.message_approved_at = None

    db.session.commit()

    flash("Outreach Review completed. Review the final outreach before approval.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

@app.route(
    "/opportunity/<int:opportunity_id>/reset-message-review",
    methods=["POST"]
)
def reset_message_review(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if opp.stage != "Ready to Send":
        flash(
            "Only Sponsor Opportunities in Outreach Preparation can be reviewed again.",
            "warning"
        )
        return redirect(
            url_for("opportunity_detail", opportunity_id=opp.id)
        )

    opp.reviewed_message = None
    opp.message_review_notes = None
    opp.message_reviewed_at = None
    opp.message_approved_at = None

    if (opp.outreach_channel or "email") == "email":
        opp.subject = None

    db.session.commit()

    flash(
        "The previous review was cleared. Review the message again before sending.",
        "success"
    )
    return redirect(
        url_for("opportunity_detail", opportunity_id=opp.id)
    )


@app.route(
    "/opportunity/<int:opportunity_id>/approve-message",
    methods=["POST"],
)
def approve_message(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not (
        opp.outreach
        and opp.reviewed_message
        and opp.message_reviewed_at
    ):
        flash(
            "Complete Outreach Review before approving outreach.",
            "warning",
        )
        return redirect(
            url_for("opportunity_detail", opportunity_id=opp.id)
        )

    if opp.message_approved_at:
        flash("Sponsor Outreach is already approved.", "info")
        return redirect(
            url_for("opportunity_detail", opportunity_id=opp.id)
        )

    opp.message_approved_at = datetime.utcnow()
    db.session.commit()

    flash(
        "Sponsor Outreach approved. It is Ready to Send.",
        "success",
    )
    return redirect(
        url_for("opportunity_detail", opportunity_id=opp.id)
    )


@app.route("/opportunity/<int:opportunity_id>/send-email", methods=["POST"])
def send_email(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not (
        opp.reviewed_message
        and opp.message_reviewed_at
        and opp.message_approved_at
    ):
        flash("Approve the reviewed outreach before sending.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    subject = (opp.subject or "").strip()
    message = (opp.reviewed_message or opp.outreach or "").strip()

    if not subject or not message:
        flash("Subject and outreach are required.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    if TEST_MODE:
        recipient = TEST_EMAIL
        subject_to_send = f"[TEST — NOT SENT TO SPONSOR] {subject}"
        delivery_mode = "TEST"
    else:
        recipient = opp.email
        subject_to_send = subject
        delivery_mode = "LIVE"

    if not recipient:
        flash("No delivery recipient is configured.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        flash("Email sending is not configured yet. Add SMTP_EMAIL and SMTP_APP_PASSWORD to .env.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    email = EmailMessage()
    email["From"] = SMTP_EMAIL
    email["To"] = recipient
    email["Subject"] = subject_to_send
    email.set_content(message)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            smtp.send_message(email)
    except Exception as e:
        flash(f"Outreach was not sent: {str(e)}", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    opp.subject = subject
    opp.outreach = message
    opp.delivery_recipient = recipient
    opp.delivery_mode = delivery_mode
    opp.stage = "Sent"
    opp.sent_date = date.today()
    opp.follow_up_date = date.today() + timedelta(days=7)

    db.session.commit()

    flash(f"{delivery_mode} outreach sent to {recipient}. Follow-Up scheduled for 7 days from today.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

@app.route("/opportunity/<int:opportunity_id>/mark-sent", methods=["POST"])
def mark_sent(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not (
        opp.reviewed_message
        and opp.message_reviewed_at
        and opp.message_approved_at
    ):
        flash("Approve the reviewed outreach before sending.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    opp.stage = "Sent"
    opp.sent_date = date.today()
    opp.follow_up_date = date.today() + timedelta(days=7)

    if opp.outreach_channel == "phone":
        opp.delivery_mode = "PHONE"
        opp.delivery_recipient = opp.phone
    elif opp.outreach_channel == "contact_form":
        opp.delivery_mode = "CONTACT_FORM"
        opp.delivery_recipient = opp.contact_url
    else:
        opp.delivery_mode = "External/manual"
        opp.delivery_recipient = opp.email

    db.session.commit()

    if opp.outreach_channel == "phone":
        flash("Outreach call sent. Follow-Up scheduled for 7 days from today.", "success")
    elif opp.outreach_channel == "contact_form":
        flash("Contact-form outreach sent. Follow-Up scheduled for 7 days from today.", "success")
    else:
        flash("Outreach sent. Follow-Up scheduled for 7 days from today.", "success")

    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


def normalize_follow_up_draft(opp, result):
    """Normalize AI follow-up output and guarantee email subject readiness."""
    generated_subject = (result.get("subject") or "").strip()
    generated_message = (result.get("message") or "").strip()
    channel = opp.outreach_channel or "email"

    if channel == "email" and not generated_subject:
        organization_name = (
            get_org_profile().get("name")
            or "our organization"
        )
        target_name = (
            opp.recommended_target
            or opp.parent_prospect
            or "the prospective sponsor"
        )

        generated_subject = (
            f"Following up: {organization_name} and {target_name}"
        )

    return {
        "subject": generated_subject,
        "message": generated_message,
    }


def apply_follow_up_draft(opp, result):
    """Replace a follow-up draft and clear stale review/completion state."""
    follow_up_draft = normalize_follow_up_draft(opp, result)

    opp.follow_up_subject = follow_up_draft["subject"]
    opp.follow_up_message = follow_up_draft["message"]
    opp.follow_up_review_notes = None
    opp.follow_up_reviewed_at = None
    opp.follow_up_completed_at = None

    return follow_up_draft


@app.route("/opportunity/<int:opportunity_id>/generate-follow-up", methods=["POST"])
def generate_follow_up(opportunity_id):
    organization = get_active_organization()
    initiative = get_active_initiative()
    opp = Opportunity.query.filter_by(
        id=opportunity_id,
        organization_id=getattr(organization, "id", None),
        initiative_id=getattr(initiative, "id", None),
    ).first_or_404()

    if not opp.follow_up_date or opp.follow_up_date > date.today():
        flash("This Sponsor Opportunity is not due for Follow-Up yet.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    from services.follow_up_generation_jobs import enqueue_job
    _, created = enqueue_job(organization, initiative, opp)
    flash(
        "Your Follow-Up Worker has started preparing the follow-up."
        if created else
        "Your Follow-Up Worker is already preparing this follow-up.",
        "success" if created else "warning",
    )
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/opportunity/<int:opportunity_id>/follow-up-status")
def follow_up_generation_status(opportunity_id):
    organization=get_active_organization();initiative=get_active_initiative()
    opp=Opportunity.query.filter_by(id=opportunity_id,organization_id=getattr(organization,"id",None),initiative_id=getattr(initiative,"id",None)).first_or_404()
    from services.follow_up_generation_jobs import get_latest_job
    job=get_latest_job(opp.id);status=getattr(job,"status","not_started")
    return jsonify({"status":status,"terminal":status in {"completed","failed"},"refresh_url":url_for("opportunity_detail",opportunity_id=opp.id)})


@app.route("/opportunity/<int:opportunity_id>/review-follow-up", methods=["POST"])
def review_follow_up(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    channel = opp.outreach_channel or "email"
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if channel == "email" and (not subject or not message):
        flash("Follow-Up subject and outreach are required before review.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    if channel != "email" and not message:
        flash("Follow-Up content is required before review.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    result = review_follow_up_quality(opp, subject, message)

    if result.get("error"):
        flash(result["error"], "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    opp.follow_up_subject = result.get("improved_subject") or subject
    opp.follow_up_message = result.get("improved_message") or message
    opp.follow_up_review_notes = json.dumps({
        "review_notes": result.get("review_notes"),
        "risk_flags": result.get("risk_flags") or []
    })
    opp.follow_up_reviewed_at = datetime.utcnow()

    db.session.commit()

    if channel == "phone":
        flash("Follow-Up reviewed. Review the final version before sending.", "success")
    elif channel == "contact_form":
        flash("Contact-form Follow-Up reviewed. Review it before sending.", "success")
    else:
        flash("Follow-Up reviewed and ready to send.", "success")

    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


def build_follow_up_email_delivery(opp):
    """Prepare reviewed follow-up email delivery details."""
    channel = (opp.outreach_channel or "email").strip().lower()

    if channel != "email":
        raise ValueError(
            "Automated follow-up email delivery is only available for email opportunities."
        )

    subject = (opp.follow_up_subject or "").strip()
    message = (opp.follow_up_message or "").strip()

    if not subject or not message:
        raise ValueError(
            "Follow-up subject and message are required before sending."
        )

    if TEST_MODE:
        recipient = (TEST_EMAIL or "").strip()
        subject_to_send = f"[TEST — NOT SENT TO SPONSOR] {subject}"
        delivery_mode = "TEST"
    else:
        recipient = (opp.email or "").strip()
        subject_to_send = subject
        delivery_mode = "LIVE"

    if not recipient:
        raise ValueError("No follow-up delivery recipient is configured.")

    return {
        "recipient": recipient,
        "subject": subject_to_send,
        "message": message,
        "delivery_mode": delivery_mode,
    }


def deliver_smtp_email(recipient, subject, message):
    """Deliver one plain-text email through the configured Gmail SMTP account."""
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        raise ValueError(
            "Email sending is not configured yet. "
            "Add SMTP_EMAIL and SMTP_APP_PASSWORD to .env."
        )

    email = EmailMessage()
    email["From"] = SMTP_EMAIL
    email["To"] = recipient
    email["Subject"] = subject
    email.set_content(message)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        smtp.send_message(email)


def record_follow_up_completion(opp):
    """Record a completed follow-up and schedule the next one."""
    opp.follow_up_completed_at = datetime.now(UTC)
    opp.follow_up_date = date.today() + timedelta(days=7)


@app.route(
    "/opportunity/<int:opportunity_id>/send-follow-up-email",
    methods=["POST"]
)
def send_follow_up_email(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not opp.follow_up_reviewed_at:
        flash("Review the Follow-Up before sending it.", "warning")
        return redirect(
            url_for("opportunity_detail", opportunity_id=opp.id)
        )

    try:
        delivery = build_follow_up_email_delivery(opp)
        deliver_smtp_email(
            delivery["recipient"],
            delivery["subject"],
            delivery["message"],
        )
    except ValueError as error:
        flash(str(error), "warning")
        return redirect(
            url_for("opportunity_detail", opportunity_id=opp.id)
        )
    except Exception as error:
        flash(f"Follow-Up was not sent: {str(error)}", "warning")
        return redirect(
            url_for("opportunity_detail", opportunity_id=opp.id)
        )

    record_follow_up_completion(opp)
    db.session.commit()

    flash(
        f'{delivery["delivery_mode"]} follow-up email sent to '
        f'{delivery["recipient"]}. The next follow-up is scheduled '
        "for 7 days from today.",
        "success",
    )
    return redirect(
        url_for("opportunity_detail", opportunity_id=opp.id)
    )


@app.route("/opportunity/<int:opportunity_id>/complete-follow-up", methods=["POST"])
def complete_follow_up(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not opp.follow_up_reviewed_at:
        flash("Review the Follow-Up before marking it complete.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    record_follow_up_completion(opp)

    db.session.commit()

    if opp.outreach_channel == "phone":
        flash("Follow-Up call sent. The next Follow-Up is scheduled for 7 days from today.", "success")
    elif opp.outreach_channel == "contact_form":
        flash("Contact-form Follow-Up sent. The next Follow-Up is scheduled for 7 days from today.", "success")
    else:
        flash("Follow-Up recorded. The next Follow-Up is scheduled for 7 days from today.", "success")

    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/opportunity/<int:opportunity_id>/update", methods=["POST"])
def update_opportunity(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    opp.stage = request.form.get("stage", opp.stage)
    opp.notes = request.form.get("notes")

    follow = request.form.get("follow_up_date")
    opp.follow_up_date = datetime.strptime(follow, "%Y-%m-%d").date() if follow else None

    db.session.commit()

    flash("Sponsor Opportunity updated.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


if os.getenv("MARSHA_SKIP_CREATE_ALL") != "1":
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    app.run(debug=True)

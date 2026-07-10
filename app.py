import os, json, smtplib
from email.message import EmailMessage
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
from openai import OpenAI
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///sponsorship.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

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

ASSETS = [
    {"name": "Presenting Partnership", "value": "Top-level association with the initiative", "capacity": "1"},
    {"name": "Category Exclusivity", "value": "Exclusive sponsor position within a business category", "capacity": "Limited"},
    {"name": "Delegate Experience Partner", "value": "Workshops, products, services, or education for delegates", "capacity": "Limited"},
    {"name": "Community Impact Partner", "value": "Visible alignment with service and community initiatives", "capacity": "Limited"},
    {"name": "Program Book Presence", "value": "Print visibility and sponsor storytelling", "capacity": "Multiple"},
    {"name": "Digital Visibility", "value": "Website, social, email, and campaign acknowledgment", "capacity": "Multiple"},
    {"name": "Event Activation", "value": "On-site display, sampling, or engagement", "capacity": "Limited"},
]

PROSPECTS = {
    "healthcare": [
        {"name": "Duke Health", "location": "Durham, NC", "category": "Healthcare & Wellness", "score": 94, "fit": "Strong local relevance and natural alignment with women’s health, wellness education, confidence, and community impact.", "angle": "Women’s Wellness and Community Impact Partner focused on preventive care, confidence, and health education."},
        {"name": "Lincoln Community Health Center", "location": "Durham, NC", "category": "Healthcare & Wellness", "score": 91, "fit": "Community-centered health mission and local relevance; strong fit for service, education, and public wellness themes.", "angle": "Community wellness partnership connected to education, screenings, or service-centered programming."},
        {"name": "UNC Health", "location": "Chapel Hill / Triangle, NC", "category": "Healthcare & Wellness", "score": 87, "fit": "Regional healthcare presence with potential alignment around women’s wellness, community service, and public education.", "angle": "Community platform for women’s wellness visibility and education."},
        {"name": "Blue Cross and Blue Shield of North Carolina", "location": "Durham, NC", "category": "Healthcare & Wellness", "score": 86, "fit": "North Carolina-based health insurer with potential community wellness, health equity, and local engagement alignment.", "angle": "Confidence, wellness, and community impact partnership with statewide relevance."},
        {"name": "YMCA of the Triangle", "location": "Triangle, NC", "category": "Healthcare & Wellness", "score": 82, "fit": "Wellness, confidence, community, and family engagement fit; potential in-kind or program partnership.", "angle": "Wellness programming, delegate fitness and wellness experiences, or community activation."}
    ],
    "beauty": [
        {"name": "Sally Beauty", "location": "Triangle / National", "category": "Beauty & Personal Care", "score": 90, "fit": "Direct alignment with pageant preparation, confidence, and beauty education.", "angle": "Product support, beauty kits, delegate experience support, or program book visibility."},
        {"name": "Ulta Beauty", "location": "Triangle / National", "category": "Beauty & Personal Care", "score": 88, "fit": "Strong alignment with beauty, confidence, self-expression, and consumer engagement.", "angle": "In-kind beauty support, gift cards, styling experience, or confidence-focused activation."},
        {"name": "Sephora", "location": "Triangle / National", "category": "Beauty & Personal Care", "score": 84, "fit": "Beauty and confidence alignment; potential for education, product support, or experience-based partnership.", "angle": "Beauty education or confidence experience for delegates."}
    ],
    "fashion": [
        {"name": "Torrid", "location": "Triangle / National", "category": "Fashion & Size-Inclusive Retail", "score": 93, "fit": "Direct size-inclusive fashion alignment with full-figured women and pageant preparation.", "angle": "Wardrobe, styling, gift cards, fashion experience, or category visibility."},
        {"name": "Lane Bryant", "location": "Triangle / National", "category": "Fashion & Size-Inclusive Retail", "score": 91, "fit": "Strong full-figured fashion and confidence alignment.", "angle": "Size-inclusive confidence and fashion partner."},
        {"name": "Ashley Stewart", "location": "Regional / National", "category": "Fashion & Size-Inclusive Retail", "score": 88, "fit": "Brand alignment with style, confidence, and full-figured women.", "angle": "Fashion sponsorship, delegate styling, or program visibility."}
    ],
    "financial": [
        {"name": "Self-Help Credit Union", "location": "Durham, NC", "category": "Financial Services", "score": 89, "fit": "Durham-based community finance alignment with empowerment, education, and local impact.", "angle": "Financial confidence or community empowerment partner."},
        {"name": "Coastal Credit Union", "location": "Triangle, NC", "category": "Financial Services", "score": 84, "fit": "Regional relevance and potential alignment with financial education and community engagement.", "angle": "Financial wellness education and visibility through the Pageant community."},
        {"name": "Truist", "location": "North Carolina / Regional", "category": "Financial Services", "score": 82, "fit": "Large regional financial institution with possible community and empowerment alignment.", "angle": "Women’s leadership, community service, and financial confidence."}
    ],
    "automotive": [
        {"name": "Mark Jacobson Toyota", "location": "Durham, NC", "category": "Automotive", "score": 84, "fit": "Local visibility and event/community sponsorship potential.", "angle": "Local presenting support, transportation visibility, or event activation."},
        {"name": "Hendrick Automotive Group", "location": "Triangle / NC", "category": "Automotive", "score": 81, "fit": "Regional automotive presence with potential community sponsorship interest.", "angle": "Mobility, community, or event visibility partner."},
        {"name": "Leith Automotive Group", "location": "Triangle, NC", "category": "Automotive", "score": 80, "fit": "Regional dealer group with event and community engagement relevance.", "angle": "Event activation and community visibility support."}
    ]
}

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
    goals = db.Column(db.Text)
    status = db.Column(db.String(50), default="Active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
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

    @property
    def sources(self):
        try:
            return json.loads(self.sources_json or "[]")
        except Exception:
            return []


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
            "goals": ""
        }

    return {
        "initiative": initiative.name,
        "target": initiative.fundraising_target or "",
        "deadline": initiative.deadline.isoformat() if initiative.deadline else "",
        "audience": initiative.audience or "",
        "needs": initiative.needs or "",
        "goals": initiative.goals or ""
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


def get_prospect_key(category, index):
    return f"{category}:{index}"

def client():
    key = os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=key) if key else None



def research_contact(prospect):
    c = client()
    if not c:
        return {"error": "OPENAI_API_KEY is not configured."}

    context = get_worker_context()

    prompt = f"""
You are the Contact Research Worker for Marsha AI's Sponsorship Coordinator.

Your task is to identify the strongest current, publicly verifiable contact path
for a sponsorship or community partnership approach.

Organization seeking sponsorship:
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

Prospect being researched:
Parent company or organization: {prospect['name']}
Location or relevance: {prospect['location']}
Category: {prospect['category']}
Why it may fit: {prospect['fit']}
Recommended sponsorship angle: {prospect['angle']}

Research the current public web and identify the best legitimate contact path
for this specific organization and initiative.

Important:
- Evaluate fit against the active initiative, audience, needs, goals, and location.
- The best target may be a local branch, subsidiary, operating unit, foundation,
  dealership, hospital, store, community office, or corporate team.
- Clearly name the best target in recommended_target.
- Never invent a person, title, email, phone number, profile, or URL.
- Prefer a named decision-maker only when publicly verifiable.
- If no named person is verifiable, identify the best department and official route.
- Do not guess email patterns.
- Distinguish clearly between the parent organization and the recommended target.
- Return only JSON with these keys:
recommended_target, contact_name, title, department, email, phone, contact_url,
linkedin_url, why_this_contact, confidence, verified_date, sources,
recommended_next_action.
- Use null for unavailable values.
- sources must be a list of objects with label and url.
"""

    try:
        response = c.responses.create(
            model="gpt-5-mini",
            tools=[{"type": "web_search"}],
            input=prompt
        )
        text = response.output_text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        return json.loads(text)
    except Exception as e:
        return {"error": f"Contact research failed: {str(e)}"}



def draft_outreach(prospect, contact):
    c = client()

    if not c:
        return "OPENAI_API_KEY is not configured. Outreach could not be drafted."

    context = get_worker_context()

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



def draft_follow_up(opp):
    c = client()

    if not c:
        return {"error": "OPENAI_API_KEY is not configured."}

    context = get_worker_context()
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
        return {"error": f"Message quality review failed: {str(e)}"}


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
                initiative=initiative
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
        initiative=initiative
    )


@app.route("/")
def home():
    return render_template("home.html", org=get_org_profile(), count=Opportunity.query.count())


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
    data = get_initiative_profile()
    session["initiative"] = data

    return render_template(
        "workspace.html",
        org=get_org_profile(),
        data=data,
        categories=CATEGORIES,
        assets=ASSETS,
        pipeline=Opportunity.query.all()
    )


@app.route("/prospects/<category>")
def prospects(category):
    return render_template("prospects.html", category=category, prospects=PROSPECTS.get(category, []))


@app.route("/prospect/<category>/<int:index>", methods=["GET", "POST"])
def prospect(category, index):
    p = PROSPECTS[category][index]

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

    prospect_key = get_prospect_key(category, index)

    research_record = ResearchRecord.query.filter_by(
        prospect_key=prospect_key
    ).first()

    contact = None
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
        contact = research_contact(p)

        if contact.get("error"):
            flash(contact["error"], "warning")
            contact = None
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
    p = PROSPECTS[category][index]
    prospect_key = get_prospect_key(category, index)

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

        flash("This opportunity is not ready to approve yet.", "warning")
        return redirect(url_for("prospect", category=category, index=index))

    existing = Opportunity.query.filter_by(
        parent_prospect=p["name"],
        contact_name=contact.get("contact_name")
    ).first()

    if existing:
        flash("This opportunity is already saved.", "warning")
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

    flash(f"{opp.recommended_target} saved as a permanent opportunity.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/pipeline")
def show_pipeline():
    opportunities = Opportunity.query.order_by(Opportunity.updated_at.desc()).all()

    return render_template(
        "pipeline.html",
        opportunities=opportunities,
        today=date.today()
    )


@app.route("/opportunity/<int:opportunity_id>")
def opportunity_detail(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

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
        stages=STAGES,
        test_mode=TEST_MODE,
        test_email=TEST_EMAIL,
        default_subject=default_subject,
        display_message=display_message,
        review_notes=review_notes,
        follow_up_due=follow_up_due,
        follow_up_review_notes=follow_up_review_notes
    )


@app.route("/opportunity/<int:opportunity_id>/review-message", methods=["POST"])
def review_message(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    channel = opp.outreach_channel or "email"

    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if channel == "email" and (not subject or not message):
        flash("Subject and message are required before review.", "warning")
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

    db.session.commit()

    flash("Message quality review completed. Review the improved version before sending.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

@app.route(
    "/opportunity/<int:opportunity_id>/reset-message-review",
    methods=["POST"]
)
def reset_message_review(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if opp.stage != "Ready to Send":
        flash(
            "Only opportunities that are ready to send can be re-reviewed.",
            "warning"
        )
        return redirect(
            url_for("opportunity_detail", opportunity_id=opp.id)
        )

    opp.reviewed_message = None
    opp.message_review_notes = None
    opp.message_reviewed_at = None

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


@app.route("/opportunity/<int:opportunity_id>/send-email", methods=["POST"])
def send_email(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not opp.message_reviewed_at:
        flash("Review the message before sending email.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    subject = (opp.subject or "").strip()
    message = (opp.reviewed_message or opp.outreach or "").strip()

    if not subject or not message:
        flash("Subject and message are required.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    if TEST_MODE:
        recipient = TEST_EMAIL
        subject_to_send = f"[TEST — NOT SENT TO PROSPECT] {subject}"
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
        flash(f"Email was not sent: {str(e)}", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    opp.subject = subject
    opp.outreach = message
    opp.delivery_recipient = recipient
    opp.delivery_mode = delivery_mode
    opp.stage = "Sent"
    opp.sent_date = date.today()
    opp.follow_up_date = date.today() + timedelta(days=7)

    db.session.commit()

    flash(f"{delivery_mode} email sent to {recipient}. Follow-up scheduled for 7 days from today.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

@app.route("/opportunity/<int:opportunity_id>/mark-sent", methods=["POST"])
def mark_sent(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not opp.message_reviewed_at:
        if opp.outreach_channel == "phone":
            flash("Review the call script before marking the call complete.", "warning")
        elif opp.outreach_channel == "contact_form":
            flash("Review the contact-form message before marking it submitted.", "warning")
        else:
            flash("Review the message before marking outreach as sent.", "warning")

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
        flash("Call marked complete. Follow-up scheduled for 7 days from today.", "success")
    elif opp.outreach_channel == "contact_form":
        flash("Contact form marked submitted. Follow-up scheduled for 7 days from today.", "success")
    else:
        flash("Outreach marked as sent. Follow-up scheduled for 7 days from today.", "success")

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
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not opp.follow_up_date or opp.follow_up_date > date.today():
        flash("This opportunity is not due for follow-up yet.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    result = draft_follow_up(opp)

    if result.get("error"):
        flash(result["error"], "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    was_regenerated = bool(opp.follow_up_message)

    apply_follow_up_draft(opp, result)

    db.session.commit()

    if was_regenerated:
        flash(
            "Follow-up draft regenerated. Review the new version before completing the follow-up.",
            "success"
        )
    else:
        flash(
            "Follow-up draft generated. Review it before completing the follow-up.",
            "success"
        )
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/opportunity/<int:opportunity_id>/review-follow-up", methods=["POST"])
def review_follow_up(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    channel = opp.outreach_channel or "email"
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if channel == "email" and (not subject or not message):
        flash("Follow-up subject and message are required before review.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    if channel != "email" and not message:
        flash("Follow-up content is required before review.", "warning")
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
        flash("Follow-up call script reviewed. Review the improved version before calling.", "success")
    elif channel == "contact_form":
        flash("Follow-up contact-form message reviewed. Review it before submitting.", "success")
    else:
        flash("Follow-up email reviewed. Review it before sending.", "success")

    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/opportunity/<int:opportunity_id>/complete-follow-up", methods=["POST"])
def complete_follow_up(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    if not opp.follow_up_reviewed_at:
        flash("Review the follow-up before marking it complete.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    opp.follow_up_completed_at = datetime.utcnow()
    opp.follow_up_date = date.today() + timedelta(days=7)

    db.session.commit()

    if opp.outreach_channel == "phone":
        flash("Follow-up call recorded. The next follow-up is scheduled for 7 days from today.", "success")
    elif opp.outreach_channel == "contact_form":
        flash("Follow-up contact form recorded. The next follow-up is scheduled for 7 days from today.", "success")
    else:
        flash("Follow-up email recorded. The next follow-up is scheduled for 7 days from today.", "success")

    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/opportunity/<int:opportunity_id>/update", methods=["POST"])
def update_opportunity(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    opp.stage = request.form.get("stage", opp.stage)
    opp.notes = request.form.get("notes")

    follow = request.form.get("follow_up_date")
    opp.follow_up_date = datetime.strptime(follow, "%Y-%m-%d").date() if follow else None

    db.session.commit()

    flash("Opportunity updated.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
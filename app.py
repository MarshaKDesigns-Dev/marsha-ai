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

ORG = {
    "name": "Ms. Full-Figured North Carolina Pageant",
    "location": "Durham, North Carolina",
    "mission": "Empower, Inspire, and Serve through confidence, leadership, community service, personal growth, and sisterhood."
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

def get_prospect_key(category, index):
    return f"{category}:{index}"

def client():
    key = os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=key) if key else None


def research_contact(prospect):
    c = client()
    if not c:
        return {"error": "OPENAI_API_KEY is not configured."}

    prompt = f"""
You are the Contact Research Worker for a sponsorship coordinator.

Organization seeking sponsorship:
{ORG['name']} in {ORG['location']}
Mission: {ORG['mission']}

Parent prospect:
Company: {prospect['name']}
Location/relevance: {prospect['location']}
Category: {prospect['category']}
Sponsorship angle: {prospect['angle']}

Research the current public web and identify the best legitimate contact path for a sponsorship or community partnership approach.

Important:
- The best target may be a local subsidiary, dealership, branch, hospital, store, or operating unit rather than the parent company.
- If so, clearly name it in recommended_target.
- Never invent a person, title, email, phone number, profile, or URL.
- Prefer an actual current decision-maker only when publicly verifiable.
- If no named person is verifiable, identify the best department and official route.
- Do not guess email patterns.
- Return only JSON with these keys:
recommended_target, contact_name, title, department, email, phone, contact_url, linkedin_url,
why_this_contact, confidence, verified_date, sources, recommended_next_action.
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

    prompt = f"""
You are the Outreach Drafting Worker for Marsha AI's Sponsorship Coordinator.

Your job is to turn verified contact research into clean, recipient-facing outreach.

Organization:
{ORG['name']}
Location: {ORG['location']}
Mission: {ORG['mission']}

Sender:
Name: {SENDER_NAME}
Title: {SENDER_TITLE}

Prospect:
Name: {prospect['name']}
Category: {prospect['category']}
Fit: {prospect['fit']}
Recommended sponsorship angle: {prospect['angle']}

Contact research:
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
- Do not include internal labels such as primary, secondary, local route, corporate route, recommended target, or contact research.
- Do not expose research notes or source language.
- If no named person is verified, use a natural role-based greeting.
- If an email is available, write a concise email.
- If there is no email but a phone number is available, write a short call script.
- If there is no email or phone number but a contact form URL is available, write a concise contact-form message.
- For contact-form messages, do not include an email subject line.
- Do not invent facts.
- Do not overpromise benefits.
- Keep the tone professional, specific, and human.
- End with the sender name, sender title, and organization name.
"""

    try:
        response = c.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        return response.output_text.strip()
    except Exception as e:
        return f"Outreach drafting failed: {str(e)}"
    
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

    channel = opp.outreach_channel or "email"

    if channel == "phone":
        prompt = f"""
You are the Message Quality Review Worker for Marsha AI's Sponsorship Coordinator.

Your job is to improve a sponsorship phone call script before the user contacts the prospect.

Organization:
{ORG['name']}
Location: {ORG['location']}
Mission: {ORG['mission']}

Opportunity:
Parent prospect: {opp.parent_prospect}
Recommended local target: {opp.recommended_target}
Decision-maker: {opp.contact_name}
Title: {opp.title}
Category: {opp.category}
Reason this contact was selected: {opp.why_this_contact}
Verified phone number: {opp.phone}

Current call script:
{message}

Rules:
- Do not invent new facts.
- Do not overpromise sponsorship benefits.
- Do not claim an existing relationship unless stated.
- Make the script sound natural when spoken aloud.
- Keep it concise, respectful, and specific.
- Make parent company vs local target clear.
- Include a clear reason for the call.
- Include a simple next step.
- Return only JSON with keys:
improved_subject, improved_message, review_notes, risk_flags.
- For phone scripts, improved_subject should be an empty string.
- risk_flags must be a list.
"""
    elif channel == "contact_form":
        prompt = f"""
You are the Message Quality Review Worker for Marsha AI's Sponsorship Coordinator.

Your job is to improve a sponsorship contact-form message before the user submits it.

Organization:
{ORG['name']}
Location: {ORG['location']}
Mission: {ORG['mission']}

Opportunity:
Parent prospect: {opp.parent_prospect}
Recommended local target: {opp.recommended_target}
Decision-maker: {opp.contact_name}
Title: {opp.title}
Category: {opp.category}
Reason this contact was selected: {opp.why_this_contact}
Contact form URL: {opp.contact_url}

Current message:
{message}

Rules:
- Do not invent new facts.
- Do not overpromise sponsorship benefits.
- Do not claim an existing relationship unless stated.
- Keep the message short enough for a contact form.
- Make the request clear.
- Include a simple next step.
- Return only JSON with keys:
improved_subject, improved_message, review_notes, risk_flags.
- For contact forms, improved_subject should be an empty string.
- risk_flags must be a list.
"""
    else:
        prompt = f"""
You are the Message Quality Review Worker for Marsha AI's Sponsorship Coordinator.

Your job is to improve a sponsorship outreach email before the user sends it.

Organization:
{ORG['name']}
Location: {ORG['location']}
Mission: {ORG['mission']}

Opportunity:
Parent prospect: {opp.parent_prospect}
Recommended local target: {opp.recommended_target}
Decision-maker: {opp.contact_name}
Title: {opp.title}
Category: {opp.category}
Reason this contact was selected: {opp.why_this_contact}

Current subject:
{subject}

Current message:
{message}

Rules:
- Do not invent new facts.
- Do not overpromise sponsorship benefits.
- Do not claim an existing relationship unless stated.
- Keep the email concise, respectful, and specific.
- Fix awkward phrasing.
- Make parent company vs local target clear.
- Keep the tone professional and human.
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

@app.route("/")
def home():
    return render_template("home.html", org=ORG, count=Opportunity.query.count())


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

    return render_template("start.html", org=ORG)


@app.route("/workspace")
def workspace():
    data = session.get("initiative")

    if not data:
        data = {
            "initiative": "2026 Ms. Full-Figured North Carolina Pageant",
            "target": "$25,000 cash + $10,000 in-kind",
            "deadline": "October 1, 2026",
            "audience": "Delegates, pageant attendees, families, supporters, local community members, social media followers, and women connected to confidence, service, and empowerment.",
            "needs": "Venue costs, printing, program book, delegate experiences, awards, photography, beauty services, fashion support, hospitality, community service support, and event production."
        }
        session["initiative"] = data

    return render_template(
        "workspace.html",
        org=ORG,
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
    return render_template("pipeline.html", opportunities=opportunities)


@app.route("/opportunity/<int:opportunity_id>")
def opportunity_detail(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    default_subject = opp.subject or f"Potential partnership with {ORG['name']}"
    display_message = (opp.reviewed_message or opp.outreach or "").replace("[Director Name]", SENDER_NAME)

    review_notes = None
    if opp.message_review_notes:
        try:
            review_notes = json.loads(opp.message_review_notes)
        except Exception:
            review_notes = None

    return render_template(
        "opportunity.html",
        opp=opp,
        stages=STAGES,
        test_mode=TEST_MODE,
        test_email=TEST_EMAIL,
        default_subject=default_subject,
        display_message=display_message,
        review_notes=review_notes
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

    if channel == "phone" and not message:
        flash("Call script is required before review.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    if channel == "contact_form" and not message:
        flash("Contact-form message is required before review.", "warning")
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

    if channel == "phone":
        flash("Call script quality review completed. Review the improved version before calling.", "success")
    elif channel == "contact_form":
        flash("Contact-form message quality review completed. Review the improved version before submitting.", "success")
    else:
        flash("Message quality review completed. Review the improved version before sending.", "success")

    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

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
import os, json, smtplib
from email.message import EmailMessage
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
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

PROSPECTS = {
    "automotive": [
        {"name":"Hendrick Automotive Group","location":"Triangle / NC","category":"Automotive","score":81,
         "fit":"Regional automotive presence with potential community sponsorship interest.",
         "angle":"Mobility, community, or event visibility partner."},
        {"name":"Mark Jacobson Toyota","location":"Durham, NC","category":"Automotive","score":84,
         "fit":"Local visibility and event/community sponsorship potential.",
         "angle":"Local presenting support, transportation visibility, or event activation."}
    ],
    "healthcare": [
        {"name":"Duke Health","location":"Durham, NC","category":"Healthcare & Wellness","score":94,
         "fit":"Strong local relevance and alignment with women’s health, wellness education, confidence, and community impact.",
         "angle":"Women’s Wellness and Community Impact Partner."},
        {"name":"Lincoln Community Health Center","location":"Durham, NC","category":"Healthcare & Wellness","score":91,
         "fit":"Community-centered health mission and strong local relevance.",
         "angle":"Community wellness and education partnership."}
    ]
}

STAGES = ["Ready to Send", "Sent", "Follow-Up Due", "Responded", "Meeting", "Proposal", "Won", "Lost"]

TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
TEST_EMAIL = os.getenv("TEST_EMAIL", "")
DIRECTOR_NAME = os.getenv("DIRECTOR_NAME", "Director Name")
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")

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
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def sources(self):
        try:
            return json.loads(self.sources_json or "[]")
        except Exception:
            return []

def client():
    key = os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=key) if key else None

def research_contact(prospect):
    c = client()
    if not c:
        return {"error":"OPENAI_API_KEY is not configured."}

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
            tools=[{"type":"web_search"}],
            input=prompt
        )
        text = response.output_text.strip()
        if text.startswith("```"):
            text = text.replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        return {"error": f"Contact research failed: {str(e)}"}

def draft_outreach(prospect, contact):
    greeting = contact.get("contact_name") or contact.get("department") or "Community Partnerships Team"
    target = contact.get("recommended_target") or prospect["name"]
    return f"""Hello {greeting},

I’m reaching out on behalf of {ORG['name']} in Durham. We are currently seeking partners for the 2026 Ms. Full-Figured North Carolina Pageant and identified {target} because {prospect['fit'].lower()}

Our platform is built around confidence, leadership, community service, and meaningful visibility for full-figured women. I believe the strongest opening would be a {prospect['angle'].lower()}

Rather than send a generic sponsorship package, I would value a short conversation to understand what matters most to your organization and determine whether there is a partnership worth building.

Would you be open to a 20-minute conversation next week?

Best,
[Director Name]
{ORG['name']}"""


def review_message_quality(opp, subject, message):
    c = client()
    if not c:
        return {"error": "OPENAI_API_KEY is not configured."}

    prompt = f"""
You are the Message Quality Review Worker for Marsha AI's Sponsorship Coordinator.

Your job is to improve a sponsorship outreach email before the Director sends it.

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
- Preserve the TEST MODE context; do not remove the fact that this will be reviewed by the Director before live sending.
- Return only JSON with keys:
improved_subject, improved_message, review_notes, risk_flags.
risk_flags must be a list.
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

@app.route("/opportunity/<int:opportunity_id>/review-message", methods=["POST"])
def review_message(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if not subject or not message:
        flash("Subject and message are required before review.", "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    result = review_message_quality(opp, subject, message)
    if result.get("error"):
        flash(result["error"], "warning")
        return redirect(url_for("opportunity_detail", opportunity_id=opp.id))

    opp.subject = result.get("improved_subject") or subject
    opp.reviewed_message = result.get("improved_message") or message
    opp.outreach = opp.reviewed_message
    notes = {
        "review_notes": result.get("review_notes"),
        "risk_flags": result.get("risk_flags") or []
    }
    opp.message_review_notes = json.dumps(notes)
    opp.message_reviewed_at = datetime.utcnow()
    db.session.commit()

    flash("Message quality review completed. Review the improved version before sending.", "success")
    return redirect(url_for("opportunity_detail", opportunity_id=opp.id))


@app.route("/")
def home():
    return render_template("home.html", org=ORG, count=Opportunity.query.count())

@app.route("/prospects/<category>")
def prospects(category):
    return render_template("prospects.html", category=category, prospects=PROSPECTS.get(category, []))

@app.route("/prospect/<category>/<int:index>", methods=["GET","POST"])
def prospect(category, index):
    p = PROSPECTS[category][index]
    contact = None

    if request.method == "POST":
        contact = research_contact(p)
        if contact.get("error"):
            flash(contact["error"], "warning")
            contact = None
        else:
            flash("Contact research completed. Review the evidence before approving.", "success")

    outreach = draft_outreach(p, contact) if contact else None
    return render_template("prospect.html", p=p, category=category, index=index, contact=contact, outreach=outreach)

@app.route("/approve/<category>/<int:index>", methods=["POST"])
def approve(category, index):
    p = PROSPECTS[category][index]
    raw = request.form.get("contact_json")
    outreach = request.form.get("outreach")

    if not raw:
        flash("Contact research must be completed before approval.", "warning")
        return redirect(url_for("prospect", category=category, index=index))

    contact = json.loads(raw)
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
    display_message = (opp.reviewed_message or opp.outreach or "").replace("[Director Name]", DIRECTOR_NAME)
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


@app.route("/opportunity/<int:opportunity_id>/send-email", methods=["POST"])
def send_email(opportunity_id):
    opp = Opportunity.query.get_or_404(opportunity_id)

    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

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
    opp.stage = "Sent"
    opp.sent_date = date.today()
    opp.follow_up_date = date.today() + timedelta(days=7)
    db.session.commit()
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

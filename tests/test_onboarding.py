from pathlib import Path

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app as app_module
from services.sponsorship_context import build_sponsorship_context


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def test_home_page_has_new_customer_setup_path():
    template = read_text("templates/home.html")

    assert "Begin Organization Setup" in template
    assert "Continue Workspace" in template
    assert "CUSTOMER ZERO" not in template
    assert "Ms. Full-Figured North Carolina Pageant" not in template


def test_navigation_exposes_core_product_pages():
    template = read_text("templates/base.html")
    workflow_navigation = read_text("services/workflow_navigation.py")

    assert "Organization" in workflow_navigation
    assert "Dashboard" in template
    assert "Pipeline" in workflow_navigation
    assert "Coming soon" in template
    assert "bootstrap.bundle.min.js" in template


def test_setup_page_collects_required_operating_context():
    template = (
        read_text("templates/setup.html")
        + read_text("templates/_sponsorship_context_fields.html")
    )

    required_fields = [
        'name="organization_name"',
        'name="organization_type"',
        'name="mission"',
        'name="sender_name"',
        'name="sender_title"',
        'name="sender_email"',
        'name="initiative_name"',
        'name="fundraising_target"',
        'name="deadline"',
        'name="audience"',
        'name="needs"',
        'name="sponsorship_needs"',
        'name="sponsorship_needs_other"',
        'name="sponsorship_needs_notes"',
        'name="geographic_scope"',
        'name="geographic_radius_miles"',
        'name="dream_sponsors"',
        'name="current_sponsors"',
        'name="existing_relationships"',
        'name="businesses_already_contacted"',
        'name="businesses_never_contact"',
        'name="goals"',
    ]

    for field in required_fields:
        assert field in template

    assert 'value="Other"' not in template
    assert "Sponsorship Needs Not Listed Above" in template
    assert 'placeholder="Enter any unlisted sponsorship needs"' in template


def test_setup_page_uses_customer_facing_intelligence_copy():
    setup = read_text("templates/setup.html")
    context = read_text("templates/_sponsorship_context_fields.html")

    assert "Tell us about your organization" in setup
    assert "Tell us about the sponsorship initiative" in setup
    assert "Success Goals" in setup
    assert "Campaign Goals" not in setup
    assert "Save Organization Intelligence" in setup
    assert "Save Changes and Return to Workspace" not in setup
    assert (
        "Marsha AI uses this information as your organization’s working"
        in setup
    )

    assert "What support would make this initiative successful?" in context
    assert (
        "identify sponsorship opportunities that fit your organization"
        in context
    )
    assert "leave this blank and allow Marsha AI to recommend" in context
    for example in (
        "Automotive",
        "Healthcare",
        "Financial Services",
        "Restaurants",
        "Retail",
        "Education",
        "Technology",
        "Hospitality",
    ):
        assert example in context
    assert (
        "If you could partner with any organization, who would be at the top"
        in context
    )
    assert 'aria-describedby="desired-sponsor-categories-help"' in context
    assert 'aria-describedby="dream-sponsors-help"' in context
    assert "for-profit business" in setup
    assert "Message Signature Preview" in setup
    assert "updateSignaturePreview" in setup


def test_setup_page_labels_remain_explicitly_associated():
    template = read_text("templates/setup.html")

    for field_id in (
        "organization_name",
        "organization_type",
        "city",
        "state",
        "mission",
        "website",
        "phone",
        "sender_name",
        "sender_title",
        "sender_email",
        "initiative_name",
        "fundraising_target",
        "deadline",
        "audience",
        "needs",
        "goals",
    ):
        assert f'for="{field_id}"' in template
        assert f'id="{field_id}"' in template


def test_workspace_uses_database_backed_organization_and_initiative():
    template = read_text("templates/workspace.html")

    assert "{{ organization.name }}" in template
    assert "{{ initiative.name }}" in template
    assert "dashboard.continue_links" in template
    assert "url_for(link.endpoint)" in template
    assert "Organization Setup" not in template


def test_workspace_route_requires_completed_setup():
    source = read_text("app.py")

    assert "if not organization or not initiative:" in source
    assert (
        '"Complete organization and sponsorship initiative setup first."'
        in source
    )
    assert 'return redirect(url_for("setup"))' in source


def setup_record_data():
    return {
        "organization_name": "Bright Futures LLC",
        "organization_type": "For-profit business",
        "city": "Durham",
        "state": "NC",
        "mission": "Create community leadership programs.",
        "website": "https://example.org",
        "phone": "919-555-0100",
        "sender_name": "Jordan Lee",
        "sender_title": "Partnerships Director",
        "sender_email": "jordan@example.org",
        "initiative_name": "Leadership Summit",
        "fundraising_target": "$25,000",
        "deadline": "2026-12-01",
        "audience": "Regional business leaders",
        "needs": "Venue and scholarships",
        "sponsorship_needs": ["Venue", "Scholarships"],
        "sponsorship_needs_other": "Childcare during sessions",
        "sponsorship_needs_notes": "Venue needed in November.",
        "desired_sponsor_categories": "Hospitality\nEducation",
        "dream_sponsors": "Example Company",
        "geographic_scope": "My State",
        "geographic_radius_miles": "",
        "current_sponsors": "Current Company",
        "existing_relationships": "Known Company",
        "businesses_already_contacted": "Contacted Company",
        "businesses_never_contact": "Excluded Company",
        "goals": "Secure sustainable partnerships.",
    }


def setup_objects(organization_type="Existing type"):
    organization = SimpleNamespace(
        id=1, name="Existing Organization", organization_type=organization_type,
        city="", state="", mission="Existing mission", sender_name="Existing",
        sender_title="Director", sender_email="", website="", phone="",
        current_sponsors_json="[]", existing_relationships_json="[]",
        businesses_already_contacted_json="[]", businesses_never_contact_json="[]",
        is_active=True, location="",
    )
    initiative = SimpleNamespace(
        id=2, organization_id=1, name="Existing Initiative",
        fundraising_target="", deadline=None, audience="", needs="", goals="",
        sponsorship_goals="", estimated_reach="", sponsorship_needs_json="[]",
        sponsorship_needs_other="", sponsorship_needs_notes="",
        desired_sponsor_categories_json="[]", geographic_scope=None,
        geographic_radius_miles=None, dream_sponsors_json="[]", status="Active",
    )
    return organization, initiative


def test_failed_setup_validation_preserves_submitted_values(monkeypatch):
    organization, initiative = setup_objects()
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    data = setup_record_data()
    data["organization_name"] = ""

    response = app_module.app.test_client().post("/setup", data=data)

    assert response.status_code == 200
    assert b"Enter your organization name." in response.data
    assert b"Childcare during sessions" in response.data
    assert b"Jordan Lee" in response.data
    assert b"Leadership Summit" in response.data


@pytest.mark.parametrize(
    "organization_type",
    (
        "Nonprofit",
        "For-profit business",
        "Public/government agency",
        "Educational institution",
        "Association",
    ),
)
def test_supported_organization_types_save_and_reach_worker_context(
    monkeypatch, organization_type
):
    organization, initiative = setup_objects()
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    monkeypatch.setattr(app_module.db.session, "flush", MagicMock())
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())
    data = setup_record_data()
    data["organization_type"] = organization_type

    response = app_module.app.test_client().post("/setup", data=data)

    assert response.status_code == 302
    assert response.location.endswith("/workspace")
    assert organization.organization_type == organization_type
    assert organization.name == "Bright Futures LLC"
    assert organization.city == "Durham"
    assert organization.state == "NC"
    assert organization.mission == "Create community leadership programs."
    assert organization.sender_name == "Jordan Lee"
    assert organization.sender_title == "Partnerships Director"
    assert organization.sender_email == "jordan@example.org"
    assert organization.website == "https://example.org"
    assert organization.phone == "919-555-0100"
    assert organization.current_sponsors_json == '["Current Company"]'
    assert organization.existing_relationships_json == '["Known Company"]'
    assert organization.businesses_already_contacted_json == '["Contacted Company"]'
    assert organization.businesses_never_contact_json == '["Excluded Company"]'
    assert initiative.name == "Leadership Summit"
    assert initiative.fundraising_target == "$25,000"
    assert initiative.deadline.isoformat() == "2026-12-01"
    assert initiative.audience == "Regional business leaders"
    assert initiative.needs == "Venue and scholarships"
    assert initiative.goals == "Secure sustainable partnerships."
    assert initiative.sponsorship_needs_json == '["Venue", "Scholarships"]'
    assert initiative.sponsorship_needs_other == "Childcare during sessions"
    assert initiative.sponsorship_needs_notes == "Venue needed in November."
    assert initiative.desired_sponsor_categories_json == '["Hospitality", "Education"]'
    assert initiative.dream_sponsors_json == '["Example Company"]'
    assert initiative.geographic_scope == "My State"
    assert initiative.geographic_radius_miles is None
    context = build_sponsorship_context(organization, initiative)
    assert context["organization_type"] == organization_type
    assert context["other_needs"] == "Childcare during sessions"
    assert context["needs_notes"] == "Venue needed in November."


def test_editing_setup_reuses_existing_records_and_reports_next_step(monkeypatch):
    organization, initiative = setup_objects()
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    organization_constructor = MagicMock()
    initiative_constructor = MagicMock()
    monkeypatch.setattr(app_module, "Organization", organization_constructor)
    monkeypatch.setattr(app_module, "SponsorshipInitiative", initiative_constructor)
    monkeypatch.setattr(app_module.db.session, "flush", MagicMock())
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())

    client = app_module.app.test_client()
    response = client.post("/setup", data=setup_record_data())

    assert response.status_code == 302
    organization_constructor.assert_not_called()
    initiative_constructor.assert_not_called()
    app_module.db.session.commit.assert_called_once_with()
    with client.session_transaction() as saved_session:
        messages = [message for _, message in saved_session.get("_flashes", [])]
    assert messages == [
        "Organization and sponsorship initiative saved. Continue on your Dashboard to review the next recommended action."
    ]
    source = Path("app.py").read_text(encoding="utf-8")
    assert "Continue on your Dashboard to review the next recommended action" in source


def test_saved_catch_all_and_signature_values_reappear_on_reopen(monkeypatch):
    organization, initiative = setup_objects()
    organization.name = "Bright Futures LLC"
    organization.sender_name = "Jordan Lee"
    organization.sender_title = "Partnerships Director"
    initiative.sponsorship_needs_other = "Childcare during sessions"
    initiative.sponsorship_needs_notes = "Venue needed in November."
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    monkeypatch.setattr(app_module, "get_sponsorship_intelligence", lambda *args: None)
    query = MagicMock()
    query.filter_by.return_value.all.return_value = []
    monkeypatch.setattr(app_module, "Opportunity", SimpleNamespace(query=query))

    response = app_module.app.test_client().get("/setup")

    assert response.status_code == 200
    assert b'value="Childcare during sessions"' in response.data
    assert b"Venue needed in November." in response.data
    assert b'value="Jordan Lee"' in response.data
    assert b'value="Partnerships Director"' in response.data
    assert b'value="Bright Futures LLC"' in response.data
    assert b"updateSignaturePreview" in response.data


def test_optional_setup_fields_may_be_blank(monkeypatch):
    organization, initiative = setup_objects()
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    monkeypatch.setattr(app_module.db.session, "flush", MagicMock())
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())
    data = {
        "organization_name": "Bright Futures",
        "mission": "Support community leaders.",
        "sender_name": "Jordan Lee",
        "sender_title": "Director",
        "initiative_name": "Leadership Summit",
    }

    response = app_module.app.test_client().post("/setup", data=data)

    assert response.status_code == 302
    assert organization.organization_type == ""
    assert organization.sender_email == ""
    assert initiative.deadline is None
    assert initiative.sponsorship_needs_other == ""


def test_invalid_deadline_is_actionable_and_preserves_submission(monkeypatch):
    organization, initiative = setup_objects()
    monkeypatch.setattr(app_module, "get_active_organization", lambda: organization)
    monkeypatch.setattr(app_module, "get_active_initiative", lambda: initiative)
    monkeypatch.setattr(app_module.db.session, "commit", MagicMock())
    data = setup_record_data()
    data["deadline"] = "December soon"

    response = app_module.app.test_client().post("/setup", data=data)

    assert response.status_code == 200
    assert b"Enter the deadline as YYYY-MM-DD." in response.data
    assert b"Childcare during sessions" in response.data
    assert app_module.db.session.commit.called is False

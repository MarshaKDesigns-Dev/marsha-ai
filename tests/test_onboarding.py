from pathlib import Path


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
    assert "Organization Setup" in template


def test_workspace_route_requires_completed_setup():
    source = read_text("app.py")

    assert "if not organization or not initiative:" in source
    assert (
        '"Complete organization and sponsorship initiative setup first."'
        in source
    )
    assert 'return redirect(url_for("setup"))' in source

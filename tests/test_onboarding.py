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

    assert "Organization" in template
    assert "Dashboard" in template
    assert "Pipeline" in template
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


def test_workspace_uses_database_backed_organization_and_initiative():
    template = read_text("templates/workspace.html")

    assert "{{ organization.name }}" in template
    assert "{{ initiative.name }}" in template
    assert "View pipeline" in template
    assert "url_for('show_pipeline')" in template
    assert "Edit setup" in template


def test_workspace_route_requires_completed_setup():
    source = read_text("app.py")

    assert "if not organization or not initiative:" in source
    assert (
        '"Complete organization and sponsorship initiative setup first."'
        in source
    )
    assert 'return redirect(url_for("setup"))' in source

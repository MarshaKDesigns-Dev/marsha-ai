from app import app

from pathlib import Path


def test_all_html_templates_compile():
    """Fail when any Jinja HTML template contains invalid syntax."""
    errors = []

    with app.app_context():
        template_names = sorted(
            name
            for name in app.jinja_env.list_templates()
            if name.endswith(".html")
        )

        assert template_names, "No HTML templates were discovered."

        for template_name in template_names:
            try:
                app.jinja_env.get_template(template_name)
            except Exception as exc:
                errors.append(
                    f"{template_name}: {type(exc).__name__}: {exc}"
                )

    assert not errors, (
        "One or more Jinja templates failed to compile:\n"
        + "\n".join(errors)
    )


def test_navigation_labels_workspace_as_dashboard():
    template = app.jinja_loader.get_source(
        app.jinja_env,
        "base.html",
    )[0]

    workspace_link = template.split(
        'aria-current="page"',
        1,
    )[1].split("</a>", 1)[0]
    assert "Dashboard" in workspace_link
    assert "sidebar-link" in template


def test_dashboard_template_keeps_worker_and_summary_sections_compact():
    template = app.jinja_loader.get_source(
        app.jinja_env,
        "workspace.html",
    )[0]

    assert "worker.detail_label" in template
    assert "worker.detail" in template
    assert "dashboard.top_priority.supporting_line" in template
    assert "Sponsors Secured" in template
    assert "organization.updated_at" in template
    assert "workflow-progress" in template
    assert "dashboard-grid" in template
    assert "manual-status-refresh" in template
    assert "dashboard.next_title" in template
    assert "dashboard.next_message" in template


def test_navigation_marks_unavailable_features_as_coming_soon():
    template = app.jinja_loader.get_source(
        app.jinja_env,
        "base.html",
    )[0]

    assert template.count("Coming soon") == 5
    assert 'aria-disabled="true"' in template
    assert "sidebar-toggle" in template
    assert "Powered by Marsha AI" in template
    assert "copy.js" in template


def test_reusable_copy_component_is_used_by_generated_content_views():
    macro = app.jinja_loader.get_source(
        app.jinja_env,
        "_copy_button.html",
    )[0]
    script = Path("static/copy.js").read_text(encoding="utf-8")
    templates = "\n".join(
        app.jinja_loader.get_source(app.jinja_env, name)[0]
        for name in (
            "prospect.html",
            "sponsorship_assets_review.html",
            "opportunity.html",
        )
    )

    assert "data-copy-target" in macro
    assert "navigator.clipboard.writeText" in script
    assert "document.execCommand" in script
    assert "Copied!" in script
    assert "copy_button" in templates


def test_prospect_review_separates_verified_information_from_assessment():
    template = app.jinja_loader.get_source(
        app.jinja_env,
        "prospect.html",
    )[0]

    assert "Verified Information" in template
    assert "MARSHA AI ASSESSMENT" in template
    assert "Why Recommended" in template
    assert "Why It Fits Your Organization" in template
    assert "Recommended Ask" in template
    assert "Why They May Say Yes" in template
    assert "RECOMMENDATION STRENGTH" in template

from app import app


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
        "url_for('workspace')",
        1,
    )[1].split("</a>", 1)[0]
    assert "Dashboard" in workspace_link
    assert 'aria-label="Workspace Dashboard"' in workspace_link


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
    assert "row-cols-2 row-cols-md-3 row-cols-xl-6" in template

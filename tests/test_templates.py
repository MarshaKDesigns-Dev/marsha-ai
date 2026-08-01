from app import app

from pathlib import Path
import re


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

    assert "dashboard.ai_team" in template
    assert "dashboard.metrics" in template
    assert "dashboard.needs_attention" in template
    assert "dashboard.recent_activity" in template
    assert "dashboard.continue_links" in template
    assert "dashboard.workflow_progress" in template
    assert "mission-workflow-progress" in template
    assert "mission-control" in template
    assert "worker.detail_label" in template
    assert "worker.detail" in template
    assert "manual-status-refresh" in template
    assert "dashboard.current_stage" in template
    assert template.count("'btn-primary'") == 1
    assert "Marsha Shearin" not in template
    assert "Ms. Full-Figured" not in template
    assert "message_reviewed" not in template
    assert "message_approved" not in template
    assert "dashboard.top_priority.action.label or 'Refresh Status'" in template
    assert "else url_for('workspace')" in template


def test_navigation_marks_unavailable_features_as_coming_soon():
    template = app.jinja_loader.get_source(
        app.jinja_env,
        "base.html",
    )[0]
    workflow_navigation = app.jinja_loader.get_source(
        app.jinja_env,
        "_workflow_navigation.html",
    )[0]

    assert template.count("Coming soon") == 2
    assert "render_workflow_navigation" in template
    assert "url_for(item.endpoint)" in workflow_navigation
    assert 'aria-disabled="true"' in workflow_navigation
    assert "Locked" in workflow_navigation
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


def test_workflow_guidance_component_is_shared_by_build_one_pages():
    macro = app.jinja_loader.get_source(
        app.jinja_env,
        "_workflow_guidance.html",
    )[0]
    integrated_templates = (
        "workspace.html",
        "strategy_work.html",
        "research_results.html",
        "pipeline.html",
        "opportunity.html",
    )

    assert "TOP PRIORITY" in macro
    assert "WORK IN PROGRESS" in macro
    assert "NEEDS ATTENTION" in macro
    assert "workflow-guidance-summary" in macro
    assert "✓ Completed" not in macro
    assert "Next Step" not in macro
    assert "primary_action_text and primary_action_url" in macro
    assert "workflow-guidance-{{ status_type }}" in macro

    for template_name in integrated_templates:
        template = app.jinja_loader.get_source(
            app.jinja_env,
            template_name,
        )[0]
        assert '"_workflow_guidance.html"' in template
        assert "workflow_guidance(" in template

    workspace = app.jinja_loader.get_source(
        app.jinja_env, "workspace.html"
    )[0]
    assert "dashboard.top_priority.message" in workspace


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


def test_workflow_pages_remove_confirmed_dead_end_and_duplicate_links():
    strategy = Path("templates/strategy_work.html").read_text(encoding="utf-8")
    pipeline = Path("templates/pipeline.html").read_text(encoding="utf-8")
    research = Path("templates/research_results.html").read_text(encoding="utf-8")

    assert strategy.count("url_for('approve_strategy_work')") == 1
    assert 'url_for(\'workspace\') }}">Return to Dashboard' in pipeline
    assert 'url_for(\'home\') }}">Return to workspace' not in pipeline
    assert "Research more for this asset" not in research
    assert research.count("Choose another asset") == 1


def test_workflow_template_destinations_exist_and_expose_return_paths():
    workflow_templates = {
        "strategy_meeting.html": "workspace",
        "strategy_work.html": "strategy_meeting",
        "sponsorship_assets_review.html": "workspace",
        "research_worker.html": "workspace",
        "research_results.html": "research_worker",
        "pipeline.html": "workspace",
        "opportunity.html": "show_pipeline",
    }
    for template_name, return_endpoint in workflow_templates.items():
        source = Path("templates", template_name).read_text(encoding="utf-8")
        endpoints = set(re.findall(r"url_for\(['\"]([^'\"]+)", source))
        assert return_endpoint in endpoints, template_name
        assert endpoints <= set(app.view_functions), template_name

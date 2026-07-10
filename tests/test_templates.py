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

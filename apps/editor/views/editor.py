"""Render the editor through the Vela template engine."""

from vela.template_engine import mark_safe, render_template


def editor_view(params: dict) -> str:
    """Render the workspace in the custom shell."""
    router = params["router"]
    help_page = render_template("apps/editor/templates/help.html", router=router)
    return render_template(
        "apps/editor/templates/index.html",
        context={"help_page": mark_safe(help_page)},
        router=router,
    )

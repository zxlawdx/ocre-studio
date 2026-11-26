"""Render the editor through the Vela template engine."""

from vela.template_engine import render_template


def editor_view(params: dict) -> str:
    """Render the workspace in the custom shell."""
    return render_template("apps/editor/templates/index.html", router=params["router"])

"""Register the standalone Ocre Studio screens."""

from apps.home.views.home import about_view, home_view, recent_view


def register_routes(router):
    for name, view, title in (
        ("home", home_view, "Início"),
        ("recent", recent_view, "Projetos recentes"),
        ("about", about_view, "Sobre"),
    ):
        router.add(f"/{name}", view, name=name, title=title, layout="blank", show_in_sidebar=False)

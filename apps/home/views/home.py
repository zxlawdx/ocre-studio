"""Render the standalone welcome, recent-project and about screens."""

from functools import partial

from vela.template_engine import mark_safe, render_template

from config.settings import APP_AUTHOR, APP_VERSION


def screen_view(params: dict, *, screen: str) -> str:
    router = params["router"]
    page = render_template(
        f"apps/home/templates/{screen}.html", context={"app_author": APP_AUTHOR}, router=router
    )
    current = {
        f"{name}_current": mark_safe('aria-current="page"' if key == screen else "")
        for name, key in (("home", "welcome"), ("recent", "recent"), ("about", "about"))
    }
    return render_template(
        "apps/home/templates/home.html",
        context={"app_version": APP_VERSION, "page_content": mark_safe(page), **current},
        router=router,
    )


home_view = partial(screen_view, screen="welcome")
recent_view = partial(screen_view, screen="recent")
about_view = partial(screen_view, screen="about")

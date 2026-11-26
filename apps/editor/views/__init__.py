from .editor import editor_view


def register_routes(router):
    router.add(
        "/editor", editor_view, name="editor", title="Editor", layout="blank", show_in_sidebar=False
    )

"""Composition root for the native Vela runtime."""

import os
import sys
from functools import partial

from vela.apps import AppConfig
from vela.core.app import VelaApp

from config.bridge import EditorBridge
from config.composition import Workspace

INSTALLED_APPS = (
    AppConfig(name="home", module="apps.home"),
    AppConfig(name="editor", module="apps.editor", persistent_modules=("apps.editor.service",)),
    AppConfig(
        name="projects", module="apps.projects", persistent_modules=("apps.projects.service",)
    ),
    AppConfig(
        name="model_library",
        module="apps.model_library",
        persistent_modules=("apps.model_library.service", "apps.model_library.kokentau"),
    ),
)


def create_app() -> VelaApp:
    """Compose services and explicitly register Vela applications."""
    workspace = Workspace()
    application = VelaApp(
        settings_module="config.settings",
        bridge_class=partial(EditorBridge, workspace=workspace),
    )
    for definition in INSTALLED_APPS:
        application.register_app(definition)
    application.lifecycle.on_shutdown(workspace.close)
    return application


def run() -> None:
    """Launch Ocre Studio through the supported Vela lifecycle."""
    if sys.platform == "win32":
        os.environ.setdefault("VELA_GUI", "edgechromium")
        from webview.platforms.winforms import renderer

        if renderer != "edgechromium":
            raise RuntimeError(
                "Instale o Microsoft Edge WebView2 Runtime para abrir o Ocre Studio."
            )
    elif sys.platform.startswith("linux"):
        os.environ.setdefault("VELA_GUI", "gtk")
    create_app().run()

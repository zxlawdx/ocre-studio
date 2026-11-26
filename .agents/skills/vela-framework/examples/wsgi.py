"""Register a native Vela app in a project generated with startproject."""

from vela.apps import AppConfig
from vela.core.app import VelaApp

INSTALLED_APPS = (AppConfig(name="home", module="apps.home"),)


def run() -> None:
    """Use the official application lifecycle."""
    application = VelaApp(settings_module="config.settings")
    for definition in INSTALLED_APPS:
        application.register_app(definition)
    application.run()

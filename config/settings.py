"""Native Vela metadata and offline desktop configuration."""

import sys

APP_TITLE = "Ocre Studio"
APP_VERSION = "0.1.0-alpha.2"
APP_AUTHOR = "Marinaldo da Costa Barroso Filho"
APP_DESCRIPTION = "Archaeological Imaging & AI"
APP_ICON = (
    "assets/icons/ocre-studio.ico" if sys.platform == "win32" else "assets/icons/ocre-studio.png"
)
APP_FILE_EXTENSIONS = [".ocre"]
ENTRY_ROUTE = "/home"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
LAYOUT = {"sidebar": False, "topbar": False, "theme": "dark"}
API = {"enabled": True, "host": "127.0.0.1", "port": 0, "auto_port": True, "docs_enabled": False}
ASSETS = {"tailwind": False}
DEBUG = False
STATIC_ROOT = "staticfiles"

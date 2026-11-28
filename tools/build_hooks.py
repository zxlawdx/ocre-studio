"""Vela build hooks that keep GTK and WebView2 distributions free of Qt."""

QT_BINDINGS = ("PyQt6", "PyQt5", "PySide6", "PySide2", "PyQtWebEngine", "qtpy")


def exclude_unused_qt(plan: dict) -> None:
    """Exclude bindings even when PyInstaller discovers optional imports."""
    if plan["gui"] not in {"gtk", "native"}:
        return
    command = plan["command"]
    for module in QT_BINDINGS:
        command[-1:-1] = ["--exclude-module", module]


def keep_model_payloads_external(plan: dict) -> None:
    """Copy application assets explicitly while leaving model checkpoints outside."""
    if "assets" in plan["folders"]:
        plan["folders"].remove("assets")
        plan["folders"].extend(
            f"assets/{folder}"
            for folder in ("icons", "legal", "dependency-notices")
            if (plan["root"] / "assets" / folder).is_dir()
        )

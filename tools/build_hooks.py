"""Vela build hooks that keep GTK and WebView2 distributions free of Qt."""

QT_BINDINGS = ("PyQt6", "PyQt5", "PySide6", "PySide2", "PyQtWebEngine", "qtpy")


def exclude_unused_qt(plan: dict) -> None:
    """Exclude bindings even when PyInstaller discovers optional imports."""
    if plan["gui"] not in {"gtk", "native"}:
        return
    command = plan["command"]
    for module in QT_BINDINGS:
        command[-1:-1] = ["--exclude-module", module]


def include_native_models(plan: dict) -> None:
    """Copy public Kokentau resources next to the executable via Vela."""
    from apps.model_library.native import BUNDLED_MODELS
    from apps.model_library.service import V7_FILES, V8_FILES

    source = plan["root"] / BUNDLED_MODELS
    for version, names in (("v7", V7_FILES), ("v8", V8_FILES)):
        folder = source / version
        if not folder.is_dir() or {entry.name for entry in folder.iterdir()} != names:
            raise ValueError(f"Provision the exact public Kokentau resources in {folder}.")
        if any(not entry.is_file() or entry.is_symlink() for entry in folder.iterdir()):
            raise ValueError(f"Unexpected Kokentau resource type in {folder}.")
    if (source / "v8/roi.json").read_text(encoding="utf-8").strip() != "{}":
        raise ValueError("The public Kokentau bundle must not include historical ROIs.")
    if "assets" in plan["folders"]:
        plan["folders"].remove("assets")
    plan["folders"].extend(
        f"assets/{folder}"
        for folder in ("icons", "legal", "dependency-notices")
        if (plan["root"] / "assets" / folder).is_dir()
    )
    plan["folders"].extend((BUNDLED_MODELS / version).as_posix() for version in ("v7", "v8"))

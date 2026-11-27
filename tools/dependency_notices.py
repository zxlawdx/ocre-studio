"""Preserve wheel notices and reject Qt bindings in release bundle trees."""

from __future__ import annotations

import argparse
import importlib.metadata
import shutil
import sys
from pathlib import Path


def collect(output: Path) -> None:
    """Copy declared wheel licenses and distribution metadata to the Vela assets."""
    output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        system = output / "system-gtk"
        system.mkdir(exist_ok=True)
        for document in Path("/usr/share/doc").glob("*/copyright"):
            if document.parent.name.startswith(
                (
                    "libgtk",
                    "libwebkit",
                    "libjavascriptcoregtk",
                    "gstreamer",
                    "libgstreamer",
                    "python3-gi",
                    "libglib",
                )
            ):
                shutil.copyfile(document, system / f"{document.parent.name}.copyright")
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        version = distribution.version
        target = output / f"{name}-{version}"
        for entry in distribution.files or ():
            parts = entry.parts
            if not parts or not parts[0].endswith(".dist-info"):
                continue
            if (
                entry.name != "METADATA"
                and "licenses" not in parts
                and not entry.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
            ):
                continue
            destination = target.joinpath(*parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(distribution.locate_file(entry), destination)


def verify(bundle: Path) -> None:
    """Reject bundled PyQt and Qt WebEngine modules, and verify notices exist."""
    bad_prefixes = ("pyqt6", "pyqt5", "pyqtwebengine", "qt6webengine", "libqt6webengine")
    if not bundle.is_dir():
        raise ValueError(f"Missing bundle: {bundle}")
    for item in bundle.rglob("*"):
        if "dependency-notices" not in item.parts and item.name.lower().replace("_", "").startswith(
            bad_prefixes
        ):
            raise ValueError(f"Unexpected Qt runtime in the official bundle: {item.name}")
    if not any((bundle / "assets/dependency-notices").glob("vela[_-]framework-*/METADATA")):
        raise ValueError("Vela notices were not copied into the bundle.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
    else:
        collect(Path("assets/dependency-notices"))

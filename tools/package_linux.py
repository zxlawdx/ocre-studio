"""Wrap the native Vela Linux bundle as DEB, RPM and AppImage."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from config.settings import APP_AUTHOR, APP_DESCRIPTION, APP_VERSION
from tools.release_artifacts import digest

SLUG = "Ocre-Studio"
DESKTOP = """[Desktop Entry]
Name=Ocre Studio
Comment=Archaeological Imaging & AI
Type=Application
Exec=ocre-studio
Icon=ocre-studio
Terminal=false
Categories=Graphics;Science;
"""
APPIMAGE_VERSION = "1.9.1"
APPIMAGE_SHA256 = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
APPIMAGE_TOOL = "appimagetool-x86_64.AppImage"


def write_executable(path: Path, text: str) -> None:
    """Write an executable launcher for an unchanged Vela bundle."""
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def prepare_tree(root: Path, bundle: Path) -> None:
    """Place the portable runtime under /opt and register the application."""
    shutil.copytree(bundle, root / "opt" / SLUG, symlinks=True)
    bin_dir = root / "usr/bin"
    desktop_dir = root / "usr/share/applications"
    icon_dir = root / "usr/share/icons/hicolor/128x128/apps"
    for directory in (bin_dir, desktop_dir, icon_dir):
        directory.mkdir(parents=True)
    write_executable(
        bin_dir / "ocre-studio",
        '#!/bin/sh\nexec /opt/Ocre-Studio/Ocre-Studio "$@"\n',
    )
    (desktop_dir / "ocre-studio.desktop").write_text(DESKTOP, encoding="utf-8")
    shutil.copyfile(bundle / "assets/icons/ocre-studio.png", icon_dir / "ocre-studio.png")


def make_deb(root: Path, dist: Path) -> None:
    """Build and inspect the Debian package."""
    control = root / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: ocre-studio\nVersion: {APP_VERSION}\nArchitecture: amd64\n"
        f"Maintainer: {APP_AUTHOR}\nDepends: libc6 (>= 2.34), libgtk-3-0, libwebkit2gtk-4.1-0, "
        f"gir1.2-gtk-3.0, gir1.2-webkit2-4.1\nDescription: {APP_DESCRIPTION}\n",
        encoding="utf-8",
    )
    target = dist / f"ocre-studio_{APP_VERSION}_amd64.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "--build", root, target], check=True)
    subprocess.run(["dpkg-deb", "--info", target], check=True)


def make_rpm(work: Path, tree: Path, dist: Path) -> None:
    """Build an x86_64 RPM from the same Vela runtime tree."""
    spec = work / "ocre-studio.spec"
    version, _, pre = APP_VERSION.partition("-")
    release = f"0.{pre}.1" if pre else "1"
    spec.write_text(
        f"""Name: ocre-studio
Version: {version}
Release: {release}
Summary: {APP_DESCRIPTION}
License: See project and bundled dependency notices
BuildArch: x86_64
AutoReqProv: no
Requires: glibc >= 2.34, gtk3, webkit2gtk4.1

%description
{APP_DESCRIPTION}

%install
mkdir -p "%{{buildroot}}"
cp -a "{tree}/opt" "{tree}/usr" "%{{buildroot}}/"

%files
/opt/Ocre-Studio
/usr/bin/ocre-studio
/usr/share/applications/ocre-studio.desktop
/usr/share/icons/hicolor/128x128/apps/ocre-studio.png
""",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "rpmbuild",
            "-bb",
            "--define",
            f"_topdir {work}",
            "--define",
            "__os_install_post %{nil}",
            spec,
        ],
        check=True,
    )
    [package] = (work / "RPMS").rglob("*.rpm")
    shutil.move(package, dist / package.name)
    subprocess.run(["rpm", "-qip", dist / package.name], check=True)


def make_appimage(work: Path, bundle: Path, dist: Path) -> None:
    """Build an AppImage using a verified official appimagetool binary."""
    tool = work / APPIMAGE_TOOL
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            APPIMAGE_VERSION,
            "--repo",
            "AppImage/appimagetool",
            "--pattern",
            APPIMAGE_TOOL,
            "--output",
            tool,
        ],
        check=True,
    )
    if digest(tool) != APPIMAGE_SHA256:
        raise ValueError("The appimagetool download did not match the pinned checksum.")
    tool.chmod(0o755)
    appdir = work / "Ocre Studio.AppDir"
    appdir.mkdir()
    shutil.copytree(bundle, appdir / SLUG, symlinks=True)
    write_executable(
        appdir / "AppRun",
        '#!/bin/sh\nroot=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'exec "$root/Ocre-Studio/Ocre-Studio" "$@"\n',
    )
    (appdir / "ocre-studio.desktop").write_text(DESKTOP, encoding="utf-8")
    shutil.copyfile(bundle / "assets/icons/ocre-studio.png", appdir / "ocre-studio.png")
    target = dist / f"Ocre-Studio-{APP_VERSION}-x86_64.AppImage"
    env = {**os.environ, "ARCH": "x86_64", "APPIMAGE_EXTRACT_AND_RUN": "1"}
    subprocess.run([tool, appdir, target], env=env, check=True)
    subprocess.run([target, "--self-test"], env=env, check=True, timeout=100)


def main() -> None:
    """Package the output of the official Vela build command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--format", nargs="+", choices=("deb", "rpm", "appimage"))
    options = parser.parse_args()
    dist = options.dist.resolve()
    bundle = dist / SLUG
    if not (bundle / ".vela-app.json").is_file():
        raise ValueError("Build the Linux bundle with Vela before packaging.")
    formats = options.format or ("deb", "rpm", "appimage")
    if {"deb", "rpm"}.intersection(formats):
        with TemporaryDirectory(prefix="ocre-linux-") as directory:
            work = Path(directory)
            tree = work / "tree"
            tree.mkdir()
            prepare_tree(tree, bundle)
            if "deb" in formats:
                make_deb(tree, dist)
            if "rpm" in formats:
                make_rpm(work, tree, dist)
    if "appimage" in formats:
        with TemporaryDirectory(prefix="ocre-appimage-") as directory:
            make_appimage(Path(directory), bundle, dist)


if __name__ == "__main__":
    main()

"""Stage and verify exactly one artifact of each required distribution format."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

PATTERNS = {
    "linux": ("Ocre-Studio-*.zip", "Ocre-Studio-*-Setup.run", "*.deb", "*.rpm", "*.AppImage"),
    "windows": ("Ocre-Studio-*.zip", "Ocre-Studio-*-Setup.exe"),
}


def artifacts(root: Path, platform: str) -> list[Path]:
    """Require every release format and reject ambiguous build directories."""
    found = []
    for pattern in (*PATTERNS[platform], "build-report*.json"):
        matches = [path for path in root.glob(pattern) if path.is_file() and path.stat().st_size]
        if len(matches) != 1:
            raise ValueError(f"{root}: expected one {pattern}; found {len(matches)}")
        found.append(matches[0])
    return found


def digest(path: Path) -> str:
    """Hash a potentially large installer without loading it into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(root: Path, platform: str, verify: bool) -> None:
    """Generate portable checksum files or reject modified release inputs."""
    selected = artifacts(root, platform)
    destination = root if verify else root / "publish"
    destination.mkdir(exist_ok=True)
    for artifact in selected:
        name = f"build-report-{platform}.json" if artifact.suffix == ".json" else artifact.name
        sidecar = destination / f"{name}.sha256"
        expected = f"{digest(artifact)}  {name}\n"
        if verify:
            if sidecar.read_text(encoding="utf-8") != expected:
                raise ValueError(f"Invalid checksum: {artifact.name}")
        else:
            shutil.copyfile(artifact, destination / name)
            sidecar.write_text(expected, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("platform", choices=PATTERNS)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    check(args.root, args.platform, args.verify)

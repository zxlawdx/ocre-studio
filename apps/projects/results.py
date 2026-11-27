"""Create immutable, versioned derivatives alongside provenance sidecars."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image

from apps.editor.service import ImageDocument
from apps.projects.catalog import atomic_json

FORMATS = {"png": ("PNG", ".png"), "jpeg": ("JPEG", ".jpg"), "tiff": ("TIFF", ".tif")}


class ResultStore:
    """Retrieve light metadata first and decode an individual result on demand."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list(self) -> list[dict]:
        """Return available result descriptions ordered from earliest to latest."""
        entries = []
        for path in self.directory.glob("*/manifest.json"):
            try:
                if path.parent.is_symlink() or path.is_symlink() or path.stat().st_size > 128_000:
                    continue
                entry = json.loads(path.read_text(encoding="utf-8"))
                if (
                    entry.get("id") != path.parent.name
                    or not re.fullmatch(r"[0-9a-f]{32}", path.parent.name)
                    or entry.get("format") not in FORMATS
                    or not re.fullmatch(r"[a-z][a-z0-9_]{0,45}", str(entry.get("technique", "")))
                    or not isinstance(entry.get("created"), str)
                ):
                    continue
                entries.append(entry)
            except (OSError, ValueError):
                continue
        return sorted(entries, key=lambda entry: entry["created"])

    def save(
        self,
        document: ImageDocument,
        format_name: str = "png",
        max_side: int = 0,
        quality: int = 92,
        base_only: bool = False,
    ) -> dict:
        """Publish a result without overwriting a prior version."""
        image = document.maps[document.selected_map] if base_only else document.render()
        if max_side:
            image = image.copy()
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        mode, extension = FORMATS[format_name]
        identifier = uuid4().hex
        metadata = {
            "id": identifier,
            "created": datetime.now(UTC).isoformat(),
            "favorite": False,
            "technique": document.selected_map,
            "format": format_name,
            "resolution": image.size,
            "source_sha256": document.sha256,
            "source": document.source.name,
            "adjustments": [
                asdict(step) for step in (() if base_only else document.history[: document.cursor])
            ],
            **document.provenance,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=self.directory) as name:
            pending = Path(name) / identifier
            pending.mkdir()
            image.save(pending / ("image" + extension), format=mode, quality=quality)
            atomic_json(pending / "manifest.json", metadata)
            pending.rename(self.directory / identifier)
        return metadata

    def find(self, identifier: str) -> dict:
        """Resolve a result identifier against published manifests."""
        for entry in self.list():
            if entry["id"] == identifier:
                return entry
        raise ValueError("Resultado indisponível.")

    def image(self, entry: dict) -> Image.Image:
        """Decode the published derivative."""
        path = self.directory / entry["id"] / ("image" + FORMATS[entry["format"]][1])
        if path.is_symlink():
            raise ValueError("Referência de resultado inválida.")
        with Image.open(path) as image:
            return image.convert("RGB")

    def update(
        self, identifier: str, name: str | None = None, favorite: bool | None = None
    ) -> dict:
        """Rename or favorite a result without modifying its pixels or provenance."""
        entry = self.find(identifier)
        if name:
            entry["name"] = name[:160]
        if favorite is not None:
            entry["favorite"] = favorite
        atomic_json(self.directory / identifier / "manifest.json", entry)
        return entry

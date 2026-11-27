"""Folder-backed photo catalogs and versioned editor state."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile

from apps.editor.service import Adjustment, ImageDocument

EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
EXCLUDED = {"resultados", "results", "thumbnails", "miniaturas", "cache", "__pycache__"}


def atomic_json(path: Path, payload: dict) -> None:
    """Replace a project or sidecar only after a complete durable write."""
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


@dataclass(slots=True)
class Session:
    """Reopen an image with bounded state and persisted, external derivatives."""

    roi: list[int] | None = None
    history: list[dict] = field(default_factory=list)
    cursor: int = 0
    result: str = "original"
    sha256: str = ""
    view: dict = field(default_factory=dict)

    def update(self, document: ImageDocument) -> None:
        """Record the active adjustments independently from the photograph."""
        self.history = [asdict(step) for step in document.history]
        self.cursor = document.cursor
        self.result = document.selected_map
        self.sha256 = document.sha256

    def restore(self, document: ImageDocument) -> None:
        """Reject stale edits when the underlying photograph has changed."""
        if self.sha256 and document.sha256 != self.sha256:
            raise ValueError("O arquivo original foi alterado desde o último salvamento.")
        for step in self.history:
            document.add(Adjustment(**step))
        document.cursor = min(self.cursor, len(document.history))


@dataclass(slots=True)
class Catalog:
    """Store references to original files and per-image state, without pixel data."""

    name: str
    root: Path
    photos: list[str]
    recursive: bool = True
    results: Path | None = None
    path: Path | None = None
    metadata: dict = field(default_factory=dict)
    sessions: dict[str, Session] = field(default_factory=dict)
    presets: dict[str, dict] = field(default_factory=dict)
    dirty: bool = True
    queue: list[dict] = field(default_factory=list)
    tabs: list[str] = field(default_factory=list)

    @classmethod
    def scan(cls, root: Path, recursive: bool = True, name: str = "") -> Catalog:
        """Index photographs without following directory or file symlinks."""
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Selecione uma pasta de fotografias.")
        catalog = cls(name or root.name, root, [], recursive, root / "Resultados")
        catalog.refresh()
        return catalog

    def refresh(self) -> None:
        """Discover new images while preserving references to missing originals."""
        photos = set(self.photos)
        excluded = self.results.resolve() if self.results else None
        for parent, directories, files in os.walk(self.root, followlinks=False):
            directory = Path(parent)
            directories[:] = [
                name
                for name in directories
                if self.recursive
                and not name.startswith(".")
                and name.casefold() not in EXCLUDED
                and not (directory / name).is_symlink()
                and directory / name != excluded
            ]
            for filename in files:
                path = directory / filename
                if (
                    path.suffix.lower() in EXTENSIONS
                    and not filename.startswith(".")
                    and not path.is_symlink()
                ):
                    photos.add(path.relative_to(self.root).as_posix())
        self.photos = sorted(photos, key=str.casefold)
        self.dirty = True

    def source(self, photo: str) -> Path:
        """Resolve a catalog identifier without accepting arbitrary bridge paths."""
        if photo not in self.photos:
            raise ValueError("Fotografia fora do catálogo.")
        path = self.root / photo
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():
            raise ValueError("A referência aponta para fora do projeto.")
        return path

    def derivative_dir(self, photo: str) -> Path:
        """Keep equal filenames in separate directories, including differing extensions."""
        source = self.source(photo).relative_to(self.root)
        suffix = hashlib.sha256(photo.encode()).hexdigest()[:12]
        return (
            (self.results or self.root / "Resultados") / source.parent / f"{source.stem}-{suffix}"
        )

    def save(self, path: Path) -> None:
        """Store a portable format while resolving paths relative to this project."""

        def relative(target: Path) -> str:
            try:
                return os.path.relpath(target, path.parent)
            except ValueError:
                return str(target)

        atomic_json(
            path,
            {
                "version": 2,
                "name": self.name,
                "root": relative(self.root),
                "results": relative(self.results or self.root / "Resultados"),
                "recursive": self.recursive,
                "photos": self.photos,
                "metadata": self.metadata,
                "presets": self.presets,
                "queue": self.queue,
                "tabs": self.tabs,
                "sessions": {key: vars_for_session(value) for key, value in self.sessions.items()},
            },
        )
        self.path = path
        self.dirty = False

    @classmethod
    def open(cls, path: Path, data: dict) -> Catalog:
        """Load catalog references and report missing originals when opened."""
        photos = data["photos"]
        if not isinstance(photos, list) or len(photos) > 100_000:
            raise ValueError("Catálogo de fotografias inválido.")
        if any(
            not isinstance(item, str) or Path(item).is_absolute() or ".." in Path(item).parts
            for item in photos
        ):
            raise ValueError("Referência de fotografia inválida.")
        return cls(
            data["name"],
            (path.parent / data["root"]).resolve(),
            photos,
            data["recursive"],
            (path.parent / data["results"]).resolve(),
            path,
            data.get("metadata", {}),
            {key: Session(**value) for key, value in data.get("sessions", {}).items()},
            data.get("presets", {}),
            False,
            data.get("queue", []) if isinstance(data.get("queue", []), list) else [],
            [key for key in data.get("tabs", []) if key in photos],
        )

    def summary(self) -> dict:
        """Return a lightweight tree input, without reading full images."""
        return {
            "name": self.name,
            "root": str(self.root),
            "photos": self.photos,
            "dirty": self.dirty,
            "presets": self.presets,
            "metadata": self.metadata,
            "tabs": self.tabs,
        }


def vars_for_session(session: Session) -> dict:
    """Serialize a session without pixel buffers."""
    return {
        "roi": session.roi,
        "history": session.history,
        "cursor": session.cursor,
        "result": session.result,
        "sha256": session.sha256,
        "view": session.view,
    }

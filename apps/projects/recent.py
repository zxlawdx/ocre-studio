"""Recently opened project files in the Vela application data directory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from vela.database import app_data_dir

from apps.projects.catalog import Catalog, atomic_json


class RecentProjects:
    """Maintain file references without deleting or moving projects."""

    def __init__(self) -> None:
        self.path = app_data_dir("Ocre-Studio") / "recent-projects.json"
        self.lock = Lock()

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("projects", [])[:12]
        except (OSError, ValueError, AttributeError, TypeError):
            return []

    def list(self) -> list[dict]:
        """Read a compact list and identify paths that no longer exist."""
        with self.lock:
            return [{**item, "missing": not Path(item["path"]).is_file()} for item in self._read()]

    def remember(self, catalog: Catalog) -> None:
        """Save a bounded recent entry after a successful open or save."""
        if catalog.path is None:
            return
        self.remember_file(catalog.path, catalog.name, catalog.root, len(catalog.photos))

    def remember_file(self, file: Path, name: str, root: Path, photos: int) -> None:
        """Record any supported project file in the shared recent-project list."""
        path = str(file.resolve())
        entry = {
            "name": name,
            "path": path,
            "root": str(root),
            "photos": photos,
            "accessed": datetime.now(UTC).isoformat(),
        }
        with self.lock:
            remaining = [item for item in self._read() if item["path"] != path]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.path, {"projects": [entry, *remaining][:12]})

    def resolve(self, key: str, remove: bool = False) -> Path:
        """Resolve only paths already present in the recent list."""
        with self.lock:
            entries = self._read()
            if any(entry["path"] == key for entry in entries):
                if remove:
                    atomic_json(
                        self.path,
                        {"projects": [entry for entry in entries if entry["path"] != key]},
                    )
                return Path(key)
        raise ValueError("Projeto recente não encontrado.")

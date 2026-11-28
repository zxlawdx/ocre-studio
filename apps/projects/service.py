"""Versioned, atomic persistence for references to original photography."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from apps.editor.service import Adjustment, ImageDocument


class ProjectRepository:
    """Store reproducible edits while leaving source files in place."""

    @staticmethod
    def save(path: Path, document: ImageDocument, selection: dict | None = None) -> None:
        """Publish a complete versioned project in one atomic replacement."""
        try:
            source = os.path.relpath(document.source, path.parent)
        except ValueError:
            source = str(document.source)
        payload = {
            "version": 1,
            "source": source,
            "sha256": document.sha256,
            "history": [asdict(step) for step in document.history],
            "cursor": document.cursor,
            "map": document.selected_map,
            "neural": document.provenance,
        }
        if selection is not None:
            payload["selection"] = selection
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            try:
                json.dump(payload, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def open(path: Path) -> tuple[ImageDocument, dict, str]:
        """Restore a project only if its original still matches the recorded hash."""
        if path.stat().st_size > 1024**2:
            raise ValueError("O arquivo de projeto excede o limite.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or len(data["history"]) > 64:
            raise ValueError("Formato de projeto incompatível.")
        document = ImageDocument.open((path.parent / data["source"]).resolve())
        if document.sha256 != data["sha256"]:
            raise ValueError("A fotografia diverge do hash registrado no projeto.")
        for step in data["history"]:
            document.add(Adjustment(**step))
        cursor = data["cursor"]
        if type(cursor) is not int or not 0 <= cursor <= len(document.history):
            raise ValueError("Histórico de projeto inválido.")
        document.cursor = cursor
        return document, data["neural"], data["map"]

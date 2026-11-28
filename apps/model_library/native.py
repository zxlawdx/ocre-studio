"""Resolve verified, pre-provisioned Kokentau payloads without a file dialog."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from apps.model_library.service import MAX_ENTRY, V7_FILES, V8_FILES, KokentauModel

BUNDLED_MODELS = Path("assets/native-models/kokentau")

V7_PAYLOAD = {
    "grade.pt": "7128b4b9e0a8f1ef4ac1c780b43d8f3f03654b3f1d90e38b4e86abd968f8281e",
    "adaptativo_v7.pt": "6f238cd7749792d05a1274970305e1771274f950e6bef9a63ca8d3f12b2bfad3",
}


def project_root() -> Path:
    """Use the executable directory for native Vela builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


class NativeModelRegistry:
    """Own the lazy, single-device native model cache."""

    def __init__(self, directory: Path | None = None) -> None:
        root = project_root()
        if directory is None:
            if configured := os.environ.get("OCRE_MODEL_DIR"):
                directory = Path(configured).expanduser()
            else:
                directory = root / BUNDLED_MODELS
                if not getattr(sys, "frozen", False) and not directory.is_dir():
                    directory = root / "native-resources/kokentau"
        self.directory = directory
        self._model: KokentauModel | None = None
        self._requested: str | None = None

    def available(self) -> bool:
        """Report provisioned files without deserializing weights or touching CUDA."""
        return all(
            (self.directory / version / name).is_file()
            for version, names in (("v7", V7_FILES), ("v8", V8_FILES))
            for name in names
        )

    def _payload(self, version: str, names: set[str]) -> dict[str, bytes]:
        payload = {}
        for name in names:
            file = self.directory / version / name
            with file.open("rb") as stream:
                data = stream.read(MAX_ENTRY + 1)
            if len(data) > MAX_ENTRY:
                raise ValueError("Um recurso Kokentau excede o tamanho autorizado.")
            payload[name] = data
        return payload

    def model(self, requested: str) -> KokentauModel:
        """Load the exact native checkpoints on demand and reuse a matching device."""
        if self._model is not None and self._requested == requested:
            return self._model
        if not self.available():
            raise ValueError("Recursos nativos Kokentau ausentes nesta instalação.")
        self.clear()
        weights = self._payload("v7", V7_FILES)
        metadata = self._payload("v8", V8_FILES)
        for name, expected in V7_PAYLOAD.items():
            if hashlib.sha256(weights[name]).hexdigest() != expected:
                raise ValueError(f"O checkpoint nativo {name} diverge da versão validada.")
        self._model = KokentauModel.from_entries(weights, metadata, requested)
        self._requested = requested
        return self._model

    def roi_spec(self, document_id: str, filename: str) -> dict | None:
        """Return an explicitly keyed historical ROI, when present in the native package."""
        if not self.available():
            return None
        data = json.loads(self._payload("v8", {"roi.json"})["roi.json"])
        spec = data.get(document_id, data.get(filename))
        return spec if isinstance(spec, dict) else None

    def clear(self) -> None:
        """Release the resident native models."""
        self._model = None
        self._requested = None

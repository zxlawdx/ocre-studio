"""Validate and run the two checkpoints required by the Kokentau V8.2 realce."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from zipfile import ZipFile

if TYPE_CHECKING:
    import numpy as np

CORE_SHA256 = "6e3039c1d8d4933bff3cfd32d1769f720774a9bb4b5a0fff3892054d278de3cd"
MAX_ENTRY = 8 * 1024**2
V7_FILES = {"grade.pt", "adaptativo_v7.pt", "manifesto_pesos.json"}
V8_FILES = {"manifesto_pesos.json", "roi.json", "modelos_utilizados.json"}


def _read_entries(path: Path, expected: set[str]) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > 64 or len(set(names)) != len(names):
            raise ValueError("Pacote contém entradas duplicadas ou excede o limite.")
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in entry.filename
                or ":" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.flag_bits & 1
                or entry.file_size > MAX_ENTRY
            ):
                raise ValueError("Entrada ZIP incompatível com a biblioteca de modelos.")
        if not expected.issubset(names):
            raise ValueError("Pacote Kokentau incompleto.")
        return {name: archive.read(name) for name in expected}


@dataclass(frozen=True, slots=True)
class ModelManifest:
    """Verified provenance for the grade and adaptive checkpoints."""

    grade_sha256: str
    adaptive_sha256: str
    epoch: int
    device: str
    version: str = "8.2"
    architecture: str = "Grade + AdaptiveV7"


class KokentauModel:
    """Keep a verified checkpoint pair resident on the selected device."""

    def __init__(self, grade: object, adaptive: object, manifest: ModelManifest) -> None:
        self._grade = grade
        self._adaptive = adaptive
        self.manifest = manifest

    @classmethod
    def load(cls, weights: Path, metadata: Path, device: str = "auto") -> KokentauModel:
        """Open the V7 and V8 packages in memory with strict tensor-only loading."""
        return cls.from_entries(
            _read_entries(weights, V7_FILES), _read_entries(metadata, V8_FILES), device
        )

    @classmethod
    def from_entries(cls, v7: dict[str, bytes], v8: dict[str, bytes], device: str) -> KokentauModel:
        """Verify the supplied payloads and load only strictly matching weights."""
        import torch

        from .kokentau.kokentau_v7_core import AdaptiveV7
        from .kokentau.legacy import Grade

        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Dispositivo inválido.")
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA indisponível.")

        descriptor = json.loads(v8["manifesto_pesos.json"])
        if descriptor.get("versao") not in {8.1, 8.2} or descriptor.get("heads") != []:
            raise ValueError("Este adaptador exige o pacote V8 sem cabeças de segmentação.")
        if not isinstance(json.loads(v8["roi.json"]), dict):
            raise ValueError("ROI inválida.")

        spec = json.loads(v7["manifesto_pesos.json"])
        grade_hash = hashlib.sha256(v7["grade.pt"]).hexdigest()
        adaptive_hash = hashlib.sha256(v7["adaptativo_v7.pt"]).hexdigest()
        if (
            spec.get("arquitetura") != "AdaptiveV7"
            or spec.get("grade_sha256") != grade_hash
            or spec.get("v7_sha256") != adaptive_hash
            or spec.get("core_sha256") != CORE_SHA256
        ):
            raise ValueError("Manifesto V7 incompatível.")

        grade_data = torch.load(BytesIO(v7["grade.pt"]), map_location="cpu", weights_only=True)
        adaptive_data = torch.load(
            BytesIO(v7["adaptativo_v7.pt"]), map_location="cpu", weights_only=True
        )
        if (
            adaptive_data.get("base_hash") != grade_hash
            or adaptive_data.get("core_hash") != CORE_SHA256
            or type(adaptive_data.get("epoca")) is not int
            or adaptive_data["epoca"] != spec.get("epoca")
        ):
            raise ValueError("Checkpoints V7 não formam um par compatível.")

        def restore(model: torch.nn.Module, data: dict) -> torch.nn.Module:
            state = data
            for key in ("modelo", "model", "state_dict", "model_state_dict"):
                if key in data:
                    state = data[key]
                    break
            model.load_state_dict(
                {
                    key.removeprefix("module.").removeprefix("_orig_mod."): value
                    for key, value in state.items()
                },
                strict=True,
            )
            return model.eval().requires_grad_(False).to(device)

        return cls(
            restore(Grade(), grade_data),
            restore(AdaptiveV7(), adaptive_data),
            ModelManifest(grade_hash, adaptive_hash, adaptive_data["epoca"], device),
        )

    def process(
        self, rgb: np.ndarray, mask: np.ndarray | None, strength: float = 0.85, block: int = 384
    ) -> dict[str, np.ndarray]:
        """Apply the reference composite to RGB uint8 pixels at native resolution."""
        from .kokentau.kokentau_v8 import enhance

        return enhance(rgb, mask, self._grade, self._adaptive, block=block, forca=strength)

    def adaptive(self, pixels: np.ndarray, mask: np.ndarray | None, block: int = 384) -> np.ndarray:
        """Expose the exact intermediate Grade + AdaptiveV7 result."""
        from .kokentau.kokentau_v7_core import infer7
        from .kokentau.kokentau_v8 import grade_img, roi_crop

        if mask is None:
            return infer7(
                self._adaptive, pixels, grade_img(self._grade, pixels, block), block=block
            )
        slices, crop, interior = roi_crop(pixels, mask)
        processed = infer7(self._adaptive, crop, grade_img(self._grade, crop, block), block=block)
        output = pixels.copy()
        output[slices][interior] = processed[interior]
        return output

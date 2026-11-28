"""Non-destructive image documents and bounded display previews."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

MAX_PIXELS = 24_000_000
MAX_REGIONS = 16


def validate_regions(boxes: list, size: tuple[int, int]) -> list[list[int]]:
    """Validate bounded selections in original image coordinates."""
    if not isinstance(boxes, list) or len(boxes) > MAX_REGIONS:
        raise ValueError("Use até 16 regiões por fotografia.")
    width, height = size
    for box in boxes:
        if not isinstance(box, list) or len(box) != 4 or any(type(n) is not int for n in box):
            raise ValueError("Região inválida.")
        x, y, right, bottom = box
        if not (0 <= x < right <= width and 0 <= y < bottom <= height):
            raise ValueError("Selecione regiões dentro da fotografia.")
    return boxes


@dataclass(frozen=True, slots=True)
class Adjustment:
    """One reproducible operation in the editor history."""

    name: str
    value: float
    replace: bool = False
    regions: list[list[int]] | None = None

    def apply(
        self, image: Image.Image, coordinate_size: tuple[int, int] | None = None
    ) -> Image.Image:
        """Apply the operation to an RGB image."""
        if self.regions:
            output = image.copy()
            width, height = size = coordinate_size or image.size
            for x, y, right, bottom in validate_regions(self.regions, size):
                box = (
                    x * image.width // width,
                    y * image.height // height,
                    (right * image.width + width - 1) // width,
                    (bottom * image.height + height - 1) // height,
                )
                output.paste(self._apply(image.crop(box)), box)
            return output
        return self._apply(image)

    def _apply(self, image: Image.Image) -> Image.Image:
        enhancers = {
            "brightness": ImageEnhance.Brightness,
            "contrast": ImageEnhance.Contrast,
            "saturation": ImageEnhance.Color,
            "sharpness": ImageEnhance.Sharpness,
        }
        if self.name in enhancers and 0 <= self.value <= 3:
            return enhancers[self.name](image).enhance(self.value)
        if self.name == "gamma" and 0.1 <= self.value <= 5:
            table = [round(255 * (index / 255) ** (1 / self.value)) for index in range(256)]
            return image.point(table * 3)
        if self.name == "channel" and self.value in (0, 1, 2):
            return image.getchannel(int(self.value)).convert("RGB")
        if self.name == "equalize" and self.value == 1:
            return ImageOps.equalize(image)
        if self.name in {"hsv", "lab"} and self.value in (0, 1, 2):
            from apps.editor.analysis import inspect_channel

            return inspect_channel(image, self.name, int(self.value))
        if self.name == "clahe" and 1 <= self.value <= 8:
            from apps.editor.analysis import local_equalization

            return local_equalization(image, self.value)
        if (self.name == "pca" and self.value in (0, 1, 2)) or (
            self.name == "decorrelation" and self.value == 1
        ):
            from apps.editor.analysis import component_view

            return component_view(image, int(self.value) if self.name == "pca" else None)
        raise ValueError("Operação ou parâmetro inválido.")


@dataclass(slots=True)
class ImageDocument:
    """Hold the untouched source and replay edits from the selected baseline."""

    source: Path
    sha256: str
    original: Image.Image
    maps: dict[str, Image.Image] = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    history: list[Adjustment] = field(default_factory=list)
    selected_map: str = "original"
    cursor: int = 0

    @classmethod
    def open(cls, path: Path) -> ImageDocument:
        """Decode a photograph and hash the same open file."""
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            stream.seek(0)
            with Image.open(stream) as image:
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("A fotografia excede o limite de 24 megapixels.")
                if image.format not in {"JPEG", "PNG", "TIFF", "WEBP"}:
                    raise ValueError("Formato de fotografia incompatível.")
                return cls(path, digest, ImageOps.exif_transpose(image).convert("RGB"))

    def add(self, step: Adjustment) -> None:
        """Validate a change before adding it to the history."""
        validate_regions(step.regions or [], self.original.size)
        step._apply(Image.new("RGB", (2, 2)))
        if self.cursor >= 64:
            raise ValueError("O histórico atingiu o limite de 64 ajustes.")
        self.history[self.cursor :] = [step]
        self.cursor += 1

    def render(self) -> Image.Image:
        """Render the full-resolution result with the active history."""
        image = self.original if self.selected_map == "original" else self.maps[self.selected_map]
        effective: list[Adjustment] = []
        for step in self.history[: self.cursor]:
            if step.replace:
                effective = [old for old in effective if old.name != step.name]
            effective.append(step)
        for step in effective:
            image = step.apply(image, self.original.size)
        return image

    def export(self, path: Path) -> None:
        """Export derived pixels without replacing any existing file."""
        formats = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF"}
        file_format = formats.get(path.suffix.lower())
        if file_format is None:
            raise ValueError("Selecione PNG, JPEG ou TIFF.")
        image = self.render()
        with path.open("xb") as output:
            try:
                image.save(output, format=file_format)
            except (OSError, ValueError):
                output.close()
                path.unlink(missing_ok=True)
                raise


def preview(image: Image.Image) -> str:
    """Encode a capped preview while keeping full-resolution pixels on the backend."""
    display = image.copy()
    display.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    with BytesIO() as output:
        display.save(output, format="JPEG", quality=91)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def histogram(image: Image.Image) -> list[list[int]]:
    """Count every pixel into three 256-bin distributions."""
    pixels = np.asarray(image)
    return [np.bincount(pixels[..., index].ravel(), minlength=256).tolist() for index in range(3)]

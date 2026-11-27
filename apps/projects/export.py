"""Export stored derivatives and provenance without re-running inference."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image, ImageDraw, ImageOps

from apps.projects.catalog import Catalog
from apps.projects.results import FORMATS, ResultStore


def export_results(catalog: Catalog, photos: list[str], destination: Path, options: dict) -> int:
    """Copy selected versions to a dedicated tree, preserving source structure."""
    mode = options.get("format", "png")
    if mode not in {*FORMATS, "json", "pdf"}:
        raise ValueError("Formato de exportação inválido.")
    quality = int(options.get("quality", 92))
    max_side = int(options.get("max_side", 0))
    if not 1 <= quality <= 100 or not 0 <= max_side <= 10000:
        raise ValueError("Qualidade ou resolução inválida.")
    records = []
    for photo in dict.fromkeys(photos):
        catalog.source(photo)
        store = ResultStore(catalog.derivative_dir(photo))
        for entry in store.list():
            if options.get("favorite") and not entry.get("favorite"):
                continue
            if options.get("technique") and entry["technique"] != options["technique"]:
                continue
            records.append((photo, store, entry))
    if not records:
        raise ValueError("Nenhum resultado atende à seleção de exportação.")
    target = destination / f"Ocre-exportacao-{uuid4().hex[:10]}"
    with TemporaryDirectory(dir=destination) as temporary:
        staging = Path(temporary) / target.name
        staging.mkdir()
        for photo, store, entry in records:
            relative = catalog.source(photo).relative_to(catalog.root)
            subdir = staging / relative.parent / relative.name
            subdir.mkdir(parents=True, exist_ok=True)
            stem = f"{entry['technique']}-{entry['id'][:12]}"
            if options.get("metadata") or mode == "json":
                (subdir / f"{stem}.json").write_text(
                    json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            if mode == "json":
                continue
            image = store.image(entry)
            if max_side:
                image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            if mode == "pdf":
                with Image.open(catalog.source(photo)) as baseline:
                    original = ImageOps.exif_transpose(baseline).convert("RGB")
                original.thumbnail((image.width, image.height), Image.Resampling.LANCZOS)
                sheet = Image.new(
                    "RGB",
                    (original.width + image.width + 32, max(original.height, image.height) + 50),
                    "white",
                )
                sheet.paste(original, (8, 36))
                sheet.paste(image, (original.width + 24, 36))
                draw = ImageDraw.Draw(sheet)
                draw.text((8, 10), "Original", fill="black")
                draw.text((original.width + 24, 10), "Resultado", fill="black")
                sheet.save(subdir / f"{stem}.pdf", format="PDF", resolution=150)
            else:
                codec, extension = FORMATS[mode]
                image.save(subdir / f"{stem}{extension}", format=codec, quality=quality)
        staging.rename(target)
    return len(records)

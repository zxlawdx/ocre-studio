"""Build and verify only the authorized Kokentau distributable payload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from apps.model_library.native import V7_PAYLOAD, NativeModelRegistry
from apps.model_library.service import MAX_ENTRY, V7_FILES, V8_FILES
from tools.release_artifacts import digest

TAG = "kokentau-v8.2-models"
WEIGHTS = "kokentau-v8.2-checkpoints.zip"
METADATA = "kokentau-v8.2-metadata.zip"


def make_zip(path: Path, files: dict[str, bytes]) -> None:
    """Write a stable ZIP using fixed timestamps and sorted members."""
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted(files.items()):
            item = ZipInfo(name)
            item.compress_type = ZIP_DEFLATED
            archive.writestr(item, payload, compresslevel=9)


def build(out: Path) -> None:
    """Copy exact tensors and generate public metadata without historical ROIs."""
    registry = NativeModelRegistry()
    model = registry.model("cpu")
    out.mkdir(parents=True, exist_ok=True)
    weights = {name: (registry.directory / "v7" / name).read_bytes() for name in V7_PAYLOAD}
    weights["manifesto_pesos.json"] = (registry.directory / "v7/manifesto_pesos.json").read_bytes()
    make_zip(out / WEIGHTS, weights)
    make_zip(
        out / METADATA,
        {
            "roi.json": b"{}\n",
            "manifesto_pesos.json": b'{"versao":8.1,"heads":[]}\n',
            "modelos_utilizados.json": json.dumps(
                {"pipeline": model.manifest.version, "architecture": model.manifest.architecture},
                sort_keys=True,
            ).encode(),
        },
    )
    public = {
        "author": "Marinaldo da Costa Barroso Filho",
        "version": model.manifest.version,
        "release": TAG,
        "assets": {name: digest(out / name) for name in (WEIGHTS, METADATA)},
        "checkpoints": V7_PAYLOAD,
    }
    (out / "kokentau-manifest.json").write_text(
        json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def recover(bundle: Path, out: Path, manifest: Path) -> None:
    """Recover only authorized model files from a previously published bundle."""
    out.mkdir(parents=True, exist_ok=True)
    with ZipFile(bundle) as archive:
        for version, names, destination in (
            ("v7", V7_FILES, WEIGHTS),
            ("v8", V8_FILES, METADATA),
        ):
            payload = {}
            for name in sorted(names):
                suffix = f"assets/native-models/kokentau/{version}/{name}"
                matches = [entry for entry in archive.infolist() if entry.filename.endswith(suffix)]
                if len(matches) != 1 or matches[0].file_size > MAX_ENTRY:
                    raise ValueError(f"Missing or ambiguous authorized model entry: {suffix}")
                payload[name] = archive.read(matches[0])
            if version == "v7":
                import hashlib

                for name, expected in V7_PAYLOAD.items():
                    if hashlib.sha256(payload[name]).hexdigest() != expected:
                        raise ValueError(f"Invalid checkpoint: {name}")
            make_zip(out / destination, payload)
    verify(out, manifest)


def verify(directory: Path, manifest: Path) -> None:
    """Compare downloaded ZIPs against the hashes in the source revision."""
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    for name in (WEIGHTS, METADATA):
        if digest(directory / name) != spec["assets"][name]:
            raise ValueError(f"SHA-256 inválido para {name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--recover-bundle", type=Path)
    options = parser.parse_args()
    if options.recover_bundle is not None:
        if options.verify is None:
            parser.error("--recover-bundle requires --verify")
        recover(options.recover_bundle, options.directory, options.verify)
    elif options.verify is None:
        build(options.directory)
    else:
        verify(options.directory, options.verify)

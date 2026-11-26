"""Extract only whitelisted and validated resources for automatic Kokentau use."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.model_library.native import NativeModelRegistry, project_root
from apps.model_library.service import V7_FILES, V8_FILES, _read_entries


def provision(weights: Path, metadata: Path, target: Path) -> None:
    """Verify both original ZIPs and install the selected entries atomically."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent, prefix=".kokentau-") as directory:
        stage = Path(directory) / "kokentau"
        for version, archive, files in (("v7", weights, V7_FILES), ("v8", metadata, V8_FILES)):
            subdir = stage / version
            subdir.mkdir(parents=True)
            for name, contents in _read_entries(archive, files).items():
                (subdir / name).write_bytes(contents)
        registry = NativeModelRegistry(stage)
        model = registry.model("cpu")
        if target.exists():
            if NativeModelRegistry(target).model("cpu").manifest != model.manifest or any(
                not (target / item.relative_to(stage)).is_file()
                or (target / item.relative_to(stage)).read_bytes() != item.read_bytes()
                for item in stage.rglob("*")
                if item.is_file()
            ):
                raise FileExistsError("O destino já contém recursos diferentes.")
        else:
            shutil.move(stage, target)
        print(f"Kokentau {model.manifest.version}: checkpoints validados e disponíveis.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("weights", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--target", type=Path, default=project_root() / "native-resources/kokentau")
    options = parser.parse_args()
    provision(options.weights, options.metadata, options.target)

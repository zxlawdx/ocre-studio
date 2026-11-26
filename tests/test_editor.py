from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from apps.editor.service import Adjustment, ImageDocument, histogram
from apps.model_library.service import _read_entries
from apps.projects.service import ProjectRepository
from config.wsgi import create_app


def test_native_routes_use_assets():
    app = create_app()
    try:
        result = app.bridge.navigate("/editor")
        assert result["ok"]
        assert 'id="photograph"' in result["html"]
        assert "editor/js/editor.js" in result["html"]
        assert app.bridge.ocre_state()["document"] is None
    finally:
        app.stop()


def test_non_destructive_export_and_project(tmp_path: Path):
    source = tmp_path / "original.png"
    Image.new("RGB", (17, 12), (32, 64, 128)).save(source)
    original = source.read_bytes()
    document = ImageDocument.open(source)
    document.add(Adjustment("brightness", 2))
    document.add(Adjustment("channel", 1))
    document.cursor = 1
    counts = histogram(document.render())
    assert [counts[channel][bin_index] for channel, bin_index in enumerate((64, 128, 255))] == [
        204,
        204,
        204,
    ]

    project = tmp_path / "test.ocre"
    ProjectRepository.save(project, document)
    reopened, provenance, selected = ProjectRepository.open(project)
    assert reopened.sha256 == sha256(original).hexdigest()
    assert reopened.cursor == 1
    assert len(reopened.history) == 2
    assert reopened.render().tobytes() == document.render().tobytes()
    assert (provenance, selected) == ({}, "original")

    destination = tmp_path / "processed.tiff"
    reopened.export(destination)
    with Image.open(destination) as image:
        assert image.size == (17, 12)
        assert image.getpixel((0, 0)) == (64, 128, 255)
    with pytest.raises(FileExistsError):
        reopened.export(source)
    assert source.read_bytes() == original


@pytest.mark.parametrize("invalid", ["../secret", "/rooted", "C:/absolute", "dir\\escape"])
def test_zip_rejects_nonlocal_paths(tmp_path: Path, invalid: str):
    path = tmp_path / "package.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("manifesto_pesos.json", "{}")
        archive.writestr(invalid, "")
    with pytest.raises(ValueError, match="Entrada ZIP"):
        _read_entries(path, {"manifesto_pesos.json"})

import pytest
from PIL import Image

from apps.editor.service import Adjustment, ImageDocument
from apps.projects.batch import Batch, Task
from apps.projects.catalog import Catalog, Session
from apps.projects.results import ResultStore


def test_catalog_excludes_derivatives_restores_relative_state_and_detects_changed_file(tmp_path):
    root = tmp_path / "research"
    for directory in ("A", "B", "Resultados", ".cache"):
        path = root / directory
        path.mkdir(parents=True)
        Image.new("RGB", (96, 80), (35, 80, 190)).save(path / "IMG.png")
    (root / "alias").symlink_to(root / "A", target_is_directory=True)
    catalog = Catalog.scan(root)
    assert catalog.photos == ["A/IMG.png", "B/IMG.png"]
    assert catalog.derivative_dir("A/IMG.png") != catalog.derivative_dir("B/IMG.png")
    document = ImageDocument.open(catalog.source("A/IMG.png"))
    document.add(Adjustment("brightness", 1.3))
    session = Session(roi=[2, 3, 34, 44])
    session.update(document)
    catalog.sessions["A/IMG.png"] = session
    catalog.presets["Suave"] = {"technique": "cromatico", "strength": 0.4}
    saved = root / "estudo.ocre"
    catalog.save(saved)
    import json

    shifted = tmp_path / "moved"
    root.rename(shifted)
    saved = shifted / saved.name
    loaded = Catalog.open(saved, json.loads(saved.read_text(encoding="utf8")))
    revised = ImageDocument.open(loaded.source("A/IMG.png"))
    loaded.sessions["A/IMG.png"].restore(revised)
    assert revised.history == document.history
    assert loaded.sessions["A/IMG.png"].roi == [2, 3, 34, 44]
    assert loaded.presets["Suave"]["strength"] == 0.4
    assert not loaded.dirty
    Image.new("RGB", (96, 80), (35, 80, 10)).save(loaded.source("A/IMG.png"))
    with pytest.raises(ValueError, match="original foi alterado"):
        loaded.sessions["A/IMG.png"].restore(ImageDocument.open(loaded.source("A/IMG.png")))


def test_results_are_append_only_and_reopen_without_inference(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 40)).save(source)
    document = ImageDocument.open(source)
    document.maps["cromatico"] = Image.new("RGB", (32, 40), "red")
    document.selected_map = "cromatico"
    document.provenance = {"roi": [0, 0, 20, 40], "strength": 0.85}
    store = ResultStore(tmp_path / "results")
    first = store.save(document)
    document.provenance["strength"] = 0.35
    second = store.save(document)
    assert first["id"] != second["id"]
    assert [result["strength"] for result in store.list()] == [0.85, 0.35]
    store.update(first["id"], "Inspeção", True)
    opened = store.find(first["id"])
    assert opened["name"] == "Inspeção" and opened["favorite"]
    assert store.image(opened).getpixel((0, 0)) == (255, 0, 0)
    assert ImageDocument.open(source).original.getpixel((0, 0)) == (0, 0, 0)


def test_batch_continues_after_failure_and_retries_only_failed_tasks():
    batch = Batch()
    batch.prepare([Task("a", "roi"), Task("broken", "roi"), Task("b", "roi"), Task("c", "roi")])
    batch.control("cancel-task", 3)
    calls = []

    def first(task):
        calls.append(task.photo)
        if task.photo == "broken":
            raise OSError("controlled failure")
        return {"id": task.photo}

    batch.run(first, lambda: None)
    assert calls == ["a", "broken", "b"]
    assert [task["state"] for task in batch.snapshot()["tasks"]] == [
        "done",
        "failed",
        "done",
        "cancelled",
    ]
    batch.prepare()
    batch.run(lambda task: {"id": task.photo}, lambda: None)
    assert [task["state"] for task in batch.snapshot()["tasks"]] == [
        "done",
        "done",
        "done",
        "cancelled",
    ]

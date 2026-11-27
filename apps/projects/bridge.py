"""Catalog, persisted results and Vela batch commands for the editor bridge."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps
from webview import FileDialog

from apps.editor.service import MAX_PIXELS, Adjustment, ImageDocument, preview
from apps.projects.batch import Task
from apps.projects.catalog import Catalog, Session
from apps.projects.export import export_results
from apps.projects.results import FORMATS, ResultStore


@lru_cache(maxsize=192)
def thumbnail(source: Path, fingerprint: tuple[int, int]) -> str:
    """Decode a bounded preview of one visible catalog item."""
    with Image.open(source) as image:
        if image.width * image.height > MAX_PIXELS:
            return ""
        image.thumbnail((176, 132))
        return preview(ImageOps.exif_transpose(image).convert("RGB"))


class CatalogCommands:
    """Extend the application bridge with native catalog workflows."""

    def _folder(self) -> Path | None:
        if self._window is None:
            raise RuntimeError("A janela nativa ainda não está disponível.")
        paths = self._window.create_file_dialog(FileDialog.FOLDER)
        return Path(paths[0]) if paths else None

    def _catalog(self) -> Catalog:
        if self._workspace.catalog is None:
            raise ValueError("Abra uma pasta como projeto.")
        return self._workspace.catalog

    def _store(self, photo: str) -> ResultStore:
        return ResultStore(self._catalog().derivative_dir(photo))

    def _switch_catalog(self, catalog: Catalog | None) -> dict:
        if self._workspace.batch.running or self._pending:
            raise ValueError("Encerre o processamento antes de trocar de projeto.")
        self._workspace.batch.restore(catalog.queue if catalog else [])
        self._batch_process = None
        self._workspace.catalog = catalog
        self._workspace.photo = None
        self._workspace.document = None
        return {
            "catalog": catalog.summary() if catalog else None,
            "clear": True,
            "queue": self._workspace.batch.snapshot(),
        }

    def ocre_recent(self) -> list[dict]:
        """List recently opened project files."""
        return self._workspace.recent.list()

    def _remember(self, catalog: Catalog) -> list[dict]:
        try:
            self._workspace.recent.remember(catalog)
        except OSError as error:
            self.logger.warning(f"Falha ao atualizar projetos recentes: {type(error).__name__}")
        return self.ocre_recent()

    def ocre_open_recent(self, key: str, remove: bool = False) -> bool:
        """Open a saved catalog or remove its reference from the recent list."""

        def open_recent() -> dict:
            path = self._workspace.recent.resolve(key, remove)
            if remove:
                return {"recent": self.ocre_recent()}
            if path.stat().st_size > 32 * 1024**2:
                raise ValueError("O projeto excede o tamanho permitido.")
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != 2:
                raise ValueError("Formato deste projeto recente incompatível.")
            catalog = Catalog.open(path, data)
            result = self._switch_catalog(catalog)
            return {**result, "recent": self._remember(catalog)}

        with self._state_lock:
            return self._run(open_recent)

    def ocre_folder(self, recursive: bool, settings: dict | None = None) -> bool:
        """Open a native folder picker and catalog originals asynchronously."""
        root = self._folder()
        if root is None:
            return False

        def scan() -> dict:
            catalog = Catalog.scan(root, recursive, (settings or {}).get("name", ""))
            if settings:
                catalog.metadata = {
                    key: str(settings.get(key, ""))[:500]
                    for key in ("site", "panel", "researcher", "notes")
                }
            return self._switch_catalog(catalog)

        with self._state_lock:
            return self._run(scan)

    def ocre_catalog_action(self, action: str) -> bool:
        """Refresh references, select a results folder or close the catalog."""
        catalog = self._catalog()
        if action == "destination":
            target = self._folder()
            if not target:
                return False
            target = target.resolve()
            if target == catalog.root or any(
                (catalog.root / photo).parent == target for photo in catalog.photos
            ):
                raise ValueError("Escolha uma pasta separada das fotografias originais.")
        else:
            target = None

        def run() -> dict:
            if action == "close":
                return self._switch_catalog(None)
            if action == "refresh":
                catalog.refresh()
            elif action == "destination":
                if self._workspace.batch.running:
                    raise ValueError("Encerre o lote antes de mudar o destino.")
                catalog.results = target
                catalog.dirty = True
            else:
                raise ValueError("Ação de catálogo inválida.")
            return {"catalog": catalog.summary()}

        with self._state_lock:
            return self._run(run)

    def ocre_photo(self, key: str) -> bool:
        """Restore a single document without loading the remaining tabs at full resolution."""
        catalog = self._catalog()
        source = catalog.source(key)

        def open_photo() -> dict:
            document = ImageDocument.open(source)
            session = catalog.sessions.setdefault(key, Session())
            session.restore(document)
            if session.result != "original":
                store = ResultStore(catalog.derivative_dir(key))
                try:
                    entry = store.find(session.result)
                    if entry["source_sha256"] == document.sha256:
                        document.maps[session.result] = store.image(entry)
                        document.selected_map = session.result
                        document.provenance = entry
                except (OSError, ValueError):
                    session.result = "original"
            self._workspace.photo = key
            self._workspace.document = document
            return {"document": self._snapshot(include_original=True)}

        with self._state_lock:
            return self._run(open_photo)

    def ocre_thumbnail(self, key: str) -> str:
        """Return one small original thumbnail on demand."""
        try:
            path = self._catalog().source(key)
            stat = path.stat()
            return thumbnail(path, (stat.st_mtime_ns, stat.st_size))
        except (OSError, ValueError):
            return ""

    def ocre_tabs(self, keys: list[str]) -> None:
        """Store tabs as catalog identifiers rather than duplicate image buffers."""
        with self._state_lock:
            catalog = self._workspace.catalog
            if catalog is None:
                return
            valid = list(dict.fromkeys(key for key in keys[:200] if key in catalog.photos))
            if valid != catalog.tabs:
                catalog.tabs = valid
                catalog.dirty = True

    def ocre_view(self, key: str, roi: list | None, view: dict) -> None:
        """Store the latest canvas state without converting it to preview pixels."""
        with self._state_lock:
            catalog = self._workspace.catalog
            if catalog is None or key != self._workspace.photo:
                return
            document = self._document()
            if roi is not None:
                if (
                    not isinstance(roi, list)
                    or len(roi) != 4
                    or any(type(item) is not int for item in roi)
                ):
                    raise ValueError("Área de análise inválida.")
                x, y, right, bottom = roi
                if not (
                    0 <= x < right <= document.original.width
                    and 0 <= y < bottom <= document.original.height
                ):
                    raise ValueError("Área fora da fotografia.")
            session = catalog.sessions.setdefault(key, Session())
            if session.roi != roi or session.view != view:
                session.roi = roi
                session.view = view
                catalog.dirty = True

    def _record(self, document: ImageDocument) -> None:
        catalog, photo = self._workspace.catalog, self._workspace.photo
        if catalog and photo:
            catalog.sessions.setdefault(photo, Session()).update(document)
            catalog.dirty = True

    def ocre_result(self, identifier: str, action: str, value: str = "") -> bool:
        """Open, compare or annotate one derivative from the active photograph."""
        photo = self._workspace.photo
        if not photo:
            raise ValueError("Selecione uma fotografia do projeto.")
        document = self._document()

        def apply() -> dict:
            store = self._store(photo)
            entry = store.find(identifier)
            if entry["source_sha256"] != document.sha256:
                raise ValueError("O resultado pertence a outra versão do original.")
            if action == "rename":
                store.update(identifier, name=value)
            elif action == "favorite":
                store.update(identifier, favorite=not entry["favorite"])
            elif action == "compare":
                image = store.image(entry)
                return {"comparison": preview(image), "comparison_size": image.size}
            elif action == "open":
                document.maps = {identifier: store.image(entry)}
                document.selected_map = identifier
                document.provenance = entry
                if entry.get("adjustments"):
                    document.history = []
                    document.cursor = 0
                self._record(document)
            else:
                raise ValueError("Ação de resultado inválida.")
            return {"document": self._snapshot()}

        with self._state_lock:
            return self._run(apply)

    def ocre_export_results(self, photos: list[str], options: dict) -> bool:
        """Export existing derivatives through a native destination picker."""
        catalog = self._catalog()
        if not photos:
            raise ValueError("Selecione fotografias para exportar.")
        target = self._folder()
        if target is None:
            return False

        def export() -> dict:
            count = export_results(catalog, photos, target, options)
            return {"message": f"{count} resultados exportados."}

        with self._state_lock:
            return self._run(export)

    def _preset_value(self, value: dict) -> dict:
        technique = value.get("technique")
        region = value.get("region", "selection")
        strength = float(value.get("strength", 0.85))
        adjustments = value.get("adjustments", [])
        if (
            technique not in self._techniques
            or not 0 <= strength <= 1
            or region not in {"selection", "full", "auto", "saved"}
            or not isinstance(adjustments, list)
            or len(adjustments) > 64
        ):
            raise ValueError("Configuração de preset inválida.")
        sample = Image.new("RGB", (2, 2))
        for item in adjustments:
            Adjustment(**item).apply(sample)
        return {
            "technique": technique,
            "region": region,
            "strength": strength,
            "adjustments": adjustments,
        }

    def ocre_preset_file(self, action: str, name: str = "") -> bool:
        """Read or write a portable, versioned preset without an embedded ROI."""
        catalog = self._catalog()
        if action == "export" and name not in catalog.presets:
            raise ValueError("Selecione um preset para exportar.")
        path = self._file(
            "Preset Ocre (*.json)", save_as="preset-ocre.json" if action == "export" else ""
        )
        if path is None:
            return False

        def exchange() -> dict:
            if action == "export":
                with path.open("x", encoding="utf-8") as stream:
                    json.dump(
                        {"version": 1, "name": name, "preset": catalog.presets[name]},
                        stream,
                        ensure_ascii=False,
                    )
                return {"message": "Preset exportado."}
            if action != "import" or path.stat().st_size > 64_000:
                raise ValueError("Arquivo de preset inválido.")
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != 1:
                raise ValueError("Versão de preset incompatível.")
            original = data["name"].strip()[:72]
            key, counter = original, 2
            while key in catalog.presets:
                key = f"{original} ({counter})"
                counter += 1
            return {
                "catalog": self.ocre_preset(key, data["preset"]),
                "message": "Preset importado.",
            }

        with self._state_lock:
            return self._run(exchange)

    def ocre_preset(self, name: str, value: dict | None) -> dict:
        """Save or delete a named preset in the active project."""
        catalog = self._catalog()
        name = name.strip()[:80]
        if not name:
            raise ValueError("Informe um nome para o preset.")
        if value is None:
            catalog.presets.pop(name, None)
        else:
            catalog.presets[name] = self._preset_value(value)
        catalog.dirty = True
        return catalog.summary()

    def ocre_batch(self, photos: list[str], techniques: list[str], options: dict) -> None:
        """Schedule a serial queue while leaving editor navigation available."""
        catalog = self._catalog()
        photos = list(dict.fromkeys(photos))
        techniques = list(dict.fromkeys(techniques))
        if not photos or not techniques:
            raise ValueError("Selecione fotografias e técnicas.")
        if len(photos) * len(techniques) > 10_000:
            raise ValueError("O lote excede 10.000 tarefas.")
        for key in photos:
            catalog.source(key)
        if any(technique not in self._techniques for technique in techniques):
            raise ValueError("Técnica de processamento desconhecida.")
        format_name = options.get("format", "png")
        max_side = int(options.get("max_side", 0))
        quality = int(options.get("quality", 92))
        strength = float(options.get("strength", 0.85))
        mode = options.get("region", "full")
        if format_name not in FORMATS or not 0 <= max_side <= 10000 or not 1 <= quality <= 100:
            raise ValueError("Configuração de saída inválida.")
        if mode not in {"full", "individual", "auto", "shared"} or not 0 <= strength <= 1:
            raise ValueError("Parâmetros do lote inválidos.")
        regions = {key: catalog.sessions.get(key, Session()).roi for key in photos}
        shared = None
        if mode == "shared":
            current = catalog.sessions.get(self._workspace.photo, Session()).roi
            if not current:
                raise ValueError("Defina uma área na fotografia de referência.")
            image = self._document().original
            shared = tuple(n / size for n, size in zip(current, (*image.size, *image.size)))
        steps = [
            Adjustment(**item)
            for item in self._preset_value(
                {
                    "technique": techniques[0],
                    "strength": strength,
                    "adjustments": options.get("adjustments", []),
                }
            )["adjustments"]
        ]

        def process(task: Task) -> dict:
            if mode == "individual" and not regions[task.photo]:
                return {}
            document = ImageDocument.open(catalog.source(task.photo))
            region = (
                regions[task.photo]
                if mode == "individual"
                else ("auto" if mode == "auto" else None)
            )
            if shared is not None:
                width, height = document.original.size
                x, y, right, bottom = (
                    round(fraction * size)
                    for fraction, size in zip(shared, (width, height, width, height))
                )
                region = [
                    min(x, width - 1),
                    min(y, height - 1),
                    max(right, x + 1),
                    max(bottom, y + 1),
                ]
            with self._workspace.inference_lock:
                self._infer(document, task.technique, strength, region, "auto", announce=False)
            for adjustment in steps:
                document.add(adjustment)
            return ResultStore(catalog.derivative_dir(task.photo)).save(
                document, format_name, max_side, quality
            )

        with self._state_lock:
            if self._workspace.batch.running:
                raise ValueError("Já existe um lote em andamento.")
            self._batch_process = process
            self._start_batch([Task(photo, method) for photo in photos for method in techniques])

    def _start_batch(self, tasks: list[Task] | None = None) -> None:
        batch = self._workspace.batch
        batch.prepare(tasks)
        try:
            self._workspace.batch_jobs.submit(batch.run, self._batch_process, self._send_batch)
        except Exception:
            batch.running = False
            raise

    def _send_batch(self) -> None:
        self.emit("ocre:batch", self._workspace.batch.snapshot())

    def ocre_batch_control(self, action: str, index: int | None = None) -> dict:
        """Control pending tasks and retry only failed entries."""
        if action == "retry":
            if getattr(self, "_batch_process", None) is None:
                raise ValueError("Execute um lote antes de tentar novamente.")
            self._start_batch()
        else:
            self._workspace.batch.control(action, index)
        return self._workspace.batch.snapshot()

    def ocre_batch_state(self) -> dict:
        """Read the current queue after navigation."""
        return self._workspace.batch.snapshot()

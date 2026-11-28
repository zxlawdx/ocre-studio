"""Native file chooser, editor commands and Vela job completion events."""

from __future__ import annotations

import json
from concurrent.futures import Future
from dataclasses import asdict
from pathlib import Path
from shutil import copyfile, rmtree
from tempfile import mkdtemp
from threading import Event, RLock
from time import perf_counter

import numpy as np
from PIL import Image
from vela.core.bridge import BaseBridge
from vela.static import StaticResolver
from webview import FileDialog

from apps.editor.service import Adjustment, ImageDocument, histogram, preview, validate_regions
from apps.model_library.service import KokentauModel
from apps.projects.bridge import CLASSIC_FILTERS, CatalogCommands
from apps.projects.catalog import Catalog, Session
from config.composition import Workspace

TUTORIAL_IMAGES = ("serra-da-capivara.jpg", "jarro-de-malqata.jpg")

NEURAL_PRESETS = {"adaptativo", "cromatico", "combinado"}
STRUCTURAL_PRESETS = {
    "estrutural",
    "blackhat",
    "tophat",
    "hessiana_escura",
    "hessiana_clara",
    "gabor",
    "suporte_estrutural",
    "roi",
}


class EditorBridge(CatalogCommands, BaseBridge):
    """Expose explicit editor actions while keeping native paths in Python."""

    _techniques = NEURAL_PRESETS | STRUCTURAL_PRESETS

    def __init__(self, router, config, workspace: Workspace) -> None:
        super().__init__(router=router, config=config)
        self._workspace = workspace
        self._state_lock = RLock()
        self._busy = False
        self._pending: dict[str, Event] = {}
        self._initial_view = True

    def _file(self, description: str, *, save_as: str = "") -> Path | None:
        if self._window is None:
            raise RuntimeError("A janela nativa ainda não está disponível.")
        paths = self._window.create_file_dialog(
            FileDialog.SAVE if save_as else FileDialog.OPEN,
            save_filename=save_as,
            file_types=(description,),
        )
        return Path(paths[0]) if paths else None

    def _document(self) -> ImageDocument:
        if self._workspace.document is None:
            raise ValueError("Abra uma fotografia.")
        return self._workspace.document

    def _snapshot(self, *, include_original: bool = False) -> dict:
        document = self._document()
        image = document.render()
        snapshot = {
            "name": document.source.name,
            "width": image.width,
            "height": image.height,
            "original_width": document.original.width,
            "original_height": document.original.height,
            "processed": preview(image),
            "histogram": histogram(image),
            "maps": ["original", *document.maps],
            "map": document.selected_map,
            "history": [asdict(step) for step in document.history[: document.cursor]],
            "provenance": document.provenance,
        }
        catalog, photo = self._workspace.catalog, self._workspace.photo
        session = (
            catalog.sessions.get(photo, Session())
            if catalog and photo
            else (self._workspace.standalone_view)
        )
        snapshot.update(
            roi=session.roi,
            regions=session.regions or ([session.roi] if session.roi else []),
            active_region=session.active_region,
            view=session.view,
        )
        if catalog and photo:
            snapshot.update(photo=photo, results=self._store(photo).list(), dirty=catalog.dirty)
        if include_original:
            snapshot["original"] = preview(document.original)
        return snapshot

    def _run(self, action, *args) -> bool:
        if self._busy:
            raise ValueError("Aguarde a conclusão da operação atual.")
        self._busy = True

        def completed(future: Future) -> None:
            with self._state_lock:
                self._busy = False
                try:
                    value = future.result()
                except ModuleNotFoundError as exc:
                    module = exc.name or "desconhecido"
                    self.logger.error(f"Dependência ausente durante o processamento: {module}")
                    self.emit("ocre:result", {"error": f"Dependência ausente: {module}."})
                except FileNotFoundError:
                    self.emit(
                        "ocre:result",
                        {
                            "error": "Arquivo não encontrado. Verifique se ele foi movido ou se a unidade está conectada."
                        },
                    )
                except PermissionError:
                    self.emit(
                        "ocre:result", {"error": "Sem permissão para acessar o arquivo ou a pasta."}
                    )
                except Exception as exc:
                    self.logger.error(f"Operação científica falhou: {type(exc).__name__}")
                    error = str(exc) if isinstance(exc, ValueError) else "Falha no processamento."
                    self.emit("ocre:result", {"error": error})
                else:
                    self.emit("ocre:result", {"result": value})

        try:
            self._workspace.jobs.submit(action, *args, on_done=completed)
        except Exception:
            self._busy = False
            raise
        return True

    def ocre_state(self) -> dict:
        """Restore displayed state after Vela navigation."""
        with self._state_lock:
            if self._busy:
                return {"busy": True}
            if self._initial_view:
                self._initial_view = False
                if self._workspace.document is None and self._workspace.catalog is None:
                    try:
                        sample = self._editor_asset("amostra-inicial.png")
                        self._workspace.document = ImageDocument.open(sample)
                    except (OSError, ValueError) as exc:
                        self.logger.warning(f"Amostra inicial indisponível: {type(exc).__name__}")
            model = self._workspace.model
            return {
                "document": self._snapshot(include_original=True)
                if self._workspace.document
                else None,
                "model": asdict(model.manifest) if model else None,
                "native_available": self._workspace.native_models.available(),
                "catalog": self._workspace.catalog.summary() if self._workspace.catalog else None,
            }

    def ocre_devices(self) -> dict:
        """Probe CUDA only when the researcher opens details."""
        try:
            import torch

            return {"cuda": torch.cuda.is_available()}
        except (ImportError, OSError, RuntimeError):
            return {"cuda": False}

    def _editor_asset(self, relative: str) -> Path:
        assets = StaticResolver.for_project(
            collected_root=self.config.get("static_root", "staticfiles"),
        )
        return assets.resolve_collected(f"editor/{relative}")

    def _load_photo(self, path: Path) -> dict:
        document = ImageDocument.open(path)
        catalog = self._workspace.catalog
        if catalog and document.source.resolve().is_relative_to(catalog.root):
            key = document.source.resolve().relative_to(catalog.root).as_posix()
            if key not in catalog.photos:
                catalog.photos = sorted([*catalog.photos, key], key=str.casefold)
                catalog.dirty = True
            self._workspace.photo = key
        else:
            self._workspace.photo = None
            self._workspace.standalone_view = Session()
        self._workspace.document = document
        return {"document": self._snapshot(include_original=True)}

    def ocre_open(self) -> bool:
        """Select a photograph in a native file dialog."""
        with self._state_lock:
            path = self._file("Fotografias (*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.webp)")
            return self._run(self._load_photo, path) if path else False

    def ocre_open_example(self, name: str) -> bool:
        """Open one of the bundled public photographs in the editor."""
        if name not in TUTORIAL_IMAGES:
            raise ValueError("Exercício desconhecido.")
        with self._state_lock:
            return self._run(self._load_photo, self._editor_asset(f"tutorial/{name}"))

    def ocre_practice_project(self) -> bool:
        """Create a writable project with the two credited teaching photographs."""
        with self._state_lock:
            parent = self._folder()
            if parent is None:
                return False

            def create() -> dict:
                path = Path(mkdtemp(prefix="Ocre-Pratica-", dir=parent))
                try:
                    for filename in (*TUTORIAL_IMAGES, "proveniencia.json"):
                        copyfile(self._editor_asset(f"tutorial/{filename}"), path / filename)
                    catalog = Catalog.scan(
                        path, recursive=False, name="Prática de realce arqueológico"
                    )
                    return {
                        **self._switch_catalog(catalog),
                        "screen": "projects",
                        "message": "Projeto de prática criado.",
                    }
                except Exception:
                    rmtree(path, ignore_errors=True)
                    raise

            return self._run(create)

    def ocre_load_model(self, device: str) -> bool:
        """Load a local V7 checkpoint pair and V8 metadata archive."""
        with self._state_lock:
            weights = self._file("Pacote de checkpoints V7 (*.zip)")
            metadata = self._file("Pacote de metadados V8 (*.zip)") if weights else None
            if metadata is None:
                return False

            def load() -> dict:
                model = KokentauModel.load(weights, metadata, device)
                self._workspace.model = model
                return {"model": asdict(model.manifest)}

            return self._run(load)

    def _region_mask(self, document: ImageDocument, region: list | str | None):
        from apps.model_library.kokentau.kokentau_v8 import auto_roi, rectmask

        pixels = np.asarray(document.original)
        mask = None
        if region == "auto":
            mask, diagnostic = auto_roi(pixels)
            if mask is None:
                raise ValueError("Nenhuma ROI automática: " + diagnostic["reason"])
        elif region == "saved":
            import cv2

            spec = self._workspace.native_models.roi_spec(document.sha256, document.source.name)
            if not spec:
                raise ValueError("Nenhuma ROI histórica para o identificador desta fotografia.")
            if "polygon" in spec:
                mask = np.zeros(pixels.shape[:2], dtype=np.uint8)
                cv2.fillPoly(mask, [np.asarray(spec["polygon"], dtype=np.int32)], 1)
                mask = mask.astype(bool)
            elif "box" in spec:
                mask = rectmask(pixels.shape, spec["box"])
            elif spec.get("aprovar_auto"):
                mask, diagnostic = auto_roi(pixels)
                if mask is None:
                    raise ValueError("Nenhuma ROI automática: " + diagnostic["reason"])
            if mask is None or not mask.any():
                raise ValueError("A ROI histórica está vazia ou não é reconhecida.")
        elif region is not None:
            rectangular = isinstance(region, list) and all(type(n) is int for n in region)
            boxes = [region] if rectangular else region
            for box in validate_regions(boxes, document.original.size):
                rectangle = rectmask(pixels.shape, box)
                mask = rectangle if mask is None else mask | rectangle
        return mask

    def _batch_filter(self, document: ImageDocument, key: str, region: list | str | None) -> None:
        start = perf_counter()
        operation, value = CLASSIC_FILTERS[key]
        source = document.original
        if region == "auto":
            mask = Image.fromarray(self._region_mask(document, region))
            bounds = mask.getbbox()
            if bounds is None:
                raise ValueError("Nenhuma região automática encontrada.")
            output = source.copy()
            filtered = Adjustment(operation, value).apply(source.crop(bounds))
            output.paste(filtered, bounds, mask.crop(bounds))
        else:
            boxes = (
                region if region and isinstance(region[0], list) else ([region] if region else None)
            )
            output = Adjustment(operation, value, regions=boxes).apply(source)
        document.maps[key] = output
        document.selected_map = key
        document.provenance = {
            "kind": "classical",
            "preset": key,
            "roi": region,
            "filter": {"name": operation, "value": value},
            "seconds": perf_counter() - start,
        }

    def _infer(
        self,
        document: ImageDocument,
        preset: str,
        strength: float,
        region: list | str | None,
        device: str,
        announce: bool = True,
    ) -> None:
        from apps.model_library.kokentau.kokentau_v8 import enhance

        if preset not in self._techniques or not 0 <= strength <= 1:
            raise ValueError("Técnica ou intensidade inválida.")
        pixels = np.asarray(document.original)
        mask = self._region_mask(document, region)

        start = perf_counter()
        model = None
        if preset in NEURAL_PRESETS:
            import torch

            if announce:
                self.emit("ocre:progress", {"message": "Carregando ferramentas de realce…"})
            registry = self._workspace.native_models

            def execute(requested: str) -> dict:
                nonlocal model
                model = registry.model(requested)
                if announce:
                    self.emit(
                        "ocre:progress",
                        {"message": f"Processando em {model.manifest.device.upper()}…"},
                    )
                if preset == "adaptativo":
                    return {preset: model.adaptive(pixels, mask)}
                return model.process(pixels, mask, strength)

            try:
                output = execute(device)
            except torch.cuda.OutOfMemoryError:
                if device != "auto":
                    raise ValueError("VRAM insuficiente. Selecione CPU ou uma ROI menor.") from None
                model = None
                registry.clear()
                torch.cuda.empty_cache()
                output = execute("cpu")
        else:
            if announce:
                self.emit("ocre:progress", {"message": "Calculando mapas estruturais…"})
            output = enhance(pixels, mask, forca=0.0)
            output = {name: output[name] for name in STRUCTURAL_PRESETS}

        document.maps = {
            name: Image.fromarray(values).convert("RGB")
            for name, values in output.items()
            if name != "original"
        }
        document.selected_map = preset
        document.provenance = {
            **(asdict(model.manifest) if model else {}),
            "kind": "neural" if preset == "adaptativo" else ("hybrid" if model else "classical"),
            "preset": preset,
            "strength": strength,
            "roi": region,
            "seconds": perf_counter() - start,
        }

    def _schedule_inference(
        self,
        document: ImageDocument,
        preset: str,
        strength: float,
        region: list | str | None,
        device: str,
    ) -> bool:
        catalog, photo = self._catalog(), self._workspace.photo
        if photo in self._pending:
            raise ValueError("Esta fotografia já está sendo processada.")
        stop = Event()
        self._pending[photo] = stop
        working = ImageDocument(document.source, document.sha256, document.original)

        def process() -> dict:
            with self._workspace.inference_lock:
                if stop.is_set():
                    return {}
                self._infer(working, preset, strength, region, device, announce=False)
            if stop.is_set():
                return {}
            from apps.projects.results import ResultStore

            return ResultStore(catalog.derivative_dir(photo)).save(working, base_only=True)

        def completed(future: Future) -> None:
            with self._state_lock:
                self._pending.pop(photo, None)
                current = self._workspace.catalog is catalog
            payload = {"photo": photo, "state": "failed", "catalog": str(catalog.root)}
            try:
                entry = future.result()
            except Exception as error:
                payload["message"] = (
                    str(error) if isinstance(error, ValueError) else "Falha ao aplicar realce."
                )
                self.logger.error(f"Processamento da fotografia falhou: {type(error).__name__}")
            else:
                payload["state"] = "done" if entry else "cancelled"
                if entry:
                    payload["id"] = entry["id"]
                    with self._state_lock:
                        session = catalog.sessions.setdefault(photo, Session())
                        session.result = entry["id"]
                        session.sha256 = document.sha256
                        catalog.dirty = True
            if current:
                self.emit("ocre:photo-processing", payload)

        try:
            self._workspace.inference_jobs.submit(process, on_done=completed)
        except Exception:
            self._pending.pop(photo, None)
            raise
        return False

    def ocre_cancel_photo(self, photo: str) -> bool:
        """Discard an outstanding individual result if it has not been written."""
        with self._state_lock:
            if photo not in self._pending:
                return False
            self._pending[photo].set()
            return True

    def ocre_infer(
        self, preset: str, strength: float, region: list | str | None, device: str
    ) -> bool:
        """Run the selected native preset against the original image."""
        with self._state_lock:
            document = self._document()
            if self._workspace.catalog and self._workspace.photo:
                return self._schedule_inference(document, preset, strength, region, device)

            def process() -> dict:
                with self._workspace.inference_lock:
                    self._infer(document, preset, strength, region, device)
                return {"document": self._snapshot()}

            return self._run(process)

    def ocre_edit(self, operation: str, value: str | float, regions: list | None = None) -> bool:
        """Adjust rendering, select a map, or move through adjustment history."""
        with self._state_lock:
            document = self._document()

            def edit() -> dict:
                if operation == "map":
                    if value != "original" and value not in document.maps:
                        raise ValueError("Mapa indisponível.")
                    document.selected_map = value
                    if self._workspace.photo and value in self._techniques:
                        entry = self._store(self._workspace.photo).save(document, base_only=True)
                        document.maps[entry["id"]] = document.maps[value]
                        document.selected_map = entry["id"]
                elif operation.startswith("set:"):
                    document.add(Adjustment(operation[4:], float(value), replace=True))
                elif operation == "paste":
                    if not isinstance(value, list) or len(value) + document.cursor > 64:
                        raise ValueError("Ajustes copiados excedem o limite do histórico.")
                    pending = [Adjustment(**item) for item in value]
                    for step in pending:
                        validate_regions(step.regions or [], document.original.size)
                        Adjustment(step.name, step.value).apply(Image.new("RGB", (2, 2)))
                    for step in pending:
                        document.add(step)
                elif operation == "history" and type(value) is int:
                    document.cursor = max(0, min(len(document.history), value))
                elif operation == "undo":
                    document.cursor = max(0, document.cursor - 1)
                elif operation == "redo":
                    document.cursor = min(len(document.history), document.cursor + 1)
                elif operation == "reset":
                    document.cursor = 0
                    document.selected_map = "original"
                else:
                    document.add(Adjustment(operation, float(value), regions=regions))
                self._record(document)
                return {"document": self._snapshot()}

            return self._run(edit)

    def ocre_project(self, action: str) -> bool:
        """Save or reopen a versioned .ocre file through native dialogs."""
        with self._state_lock:
            if action in {"save", "save-as"}:
                catalog = self._workspace.catalog
                document = self._workspace.document
                if catalog is None and document is None:
                    raise ValueError("Abra um projeto ou uma fotografia.")
                path = (
                    catalog.path
                    if catalog and catalog.path and action == "save"
                    else self._file("Projeto Ocre (*.ocre)", save_as="projeto.ocre")
                )
                if path is None:
                    return False

                def save() -> dict:
                    if path.suffix.lower() != ".ocre":
                        raise ValueError("Use a extensão .ocre no nome do projeto.")
                    if catalog is not None:
                        catalog.queue = self._workspace.batch.snapshot()["tasks"]
                        catalog.save(path)
                        return {
                            "catalog": catalog.summary(),
                            "message": "Projeto salvo.",
                            "recent": self._remember(catalog),
                        }
                    if path.resolve() == document.source.resolve():
                        raise ValueError("O projeto não pode sobrescrever a fotografia.")
                    session = self._workspace.standalone_view
                    self._workspace.projects.save(
                        path,
                        document,
                        {
                            "regions": session.regions,
                            "active": session.active_region,
                            "view": session.view,
                        },
                    )
                    return {
                        "message": "Projeto salvo.",
                        "recent": self._remember_single(path, document),
                    }

                return self._run(save)
            if action != "open":
                raise ValueError("Ação de projeto inválida.")
            path = self._file("Projeto Ocre (*.ocre)")
            if path is None:
                return False

            return self._run(self._load_project, path)

    def _remember_single(self, path: Path, document: ImageDocument) -> list[dict]:
        try:
            self._workspace.recent.remember_file(path, path.stem, document.source.parent, 1)
        except OSError as error:
            self.logger.warning(f"Falha ao atualizar projetos recentes: {type(error).__name__}")
        return self.ocre_recent()

    def _load_project(self, path: Path) -> dict:
        if path.stat().st_size > 32 * 1024**2:
            raise ValueError("O projeto excede o tamanho permitido.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") == 2:
            catalog = Catalog.open(path, data)
            result = self._switch_catalog(catalog)
            return {**result, "recent": self._remember(catalog)}
        document, provenance, selected = self._workspace.projects.open(path)
        if provenance:
            hashes = ("grade_sha256", "adaptive_sha256")
            if any(key in provenance for key in hashes):
                model = self._workspace.native_models.model("auto")
                if any(getattr(model.manifest, key) != provenance.get(key) for key in hashes):
                    raise ValueError("O par nativo não corresponde aos hashes do projeto.")
            with self._workspace.inference_lock:
                self._infer(
                    document,
                    provenance.get("preset", "combinado"),
                    provenance["strength"],
                    provenance["roi"],
                    "auto",
                )
        if selected != "original" and selected not in document.maps:
            raise ValueError("O projeto referencia um mapa indisponível.")
        document.selected_map = selected
        selection = data.get("selection", {})
        if not isinstance(selection, dict):
            raise ValueError("Seleção do projeto inválida.")
        regions = validate_regions(selection.get("regions", []), document.original.size)
        active = selection.get("active", 0)
        view = selection.get("view", {})
        if (
            type(active) is not int
            or not 0 <= active < max(1, len(regions))
            or not isinstance(view, dict)
        ):
            raise ValueError("Seleção do projeto inválida.")
        state = self._switch_catalog(None)
        self._workspace.document = document
        self._workspace.standalone_view = Session(
            roi=regions[active] if regions else None,
            regions=regions,
            active_region=active,
            view=view,
        )
        return {
            **state,
            "clear": False,
            "document": self._snapshot(include_original=True),
            "recent": self._remember_single(path, document),
        }

    def ocre_export(self) -> bool:
        """Export the displayed result without overwriting an existing file."""
        with self._state_lock:
            document = self._document()
            path = self._file("Imagem processada (*.png;*.jpg;*.tif)", save_as="realce.png")
            if path is None:
                return False

            def export() -> dict:
                try:
                    document.export(path if path.suffix else path.with_suffix(".png"))
                except FileExistsError as exc:
                    raise ValueError("Já existe um arquivo com esse nome.") from exc
                return {"message": "Imagem exportada."}

            return self._run(export)

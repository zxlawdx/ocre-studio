"""Native file chooser, editor commands and Vela job completion events."""

from __future__ import annotations

import json
from concurrent.futures import Future
from dataclasses import asdict
from pathlib import Path
from threading import Event, RLock
from time import perf_counter

import numpy as np
from PIL import Image
from vela.core.bridge import BaseBridge
from webview import FileDialog

from apps.editor.service import Adjustment, ImageDocument, histogram, preview
from apps.model_library.service import KokentauModel
from apps.projects.bridge import CatalogCommands
from apps.projects.catalog import Catalog, Session
from config.composition import Workspace

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
        if catalog and photo:
            session = catalog.sessions.get(photo, Session())
            snapshot.update(
                photo=photo,
                roi=session.roi,
                view=session.view,
                results=self._store(photo).list(),
                dirty=catalog.dirty,
            )
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

    def ocre_open(self) -> bool:
        """Select a photograph in a native file dialog."""
        with self._state_lock:
            path = self._file("Fotografias (*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.webp)")
            if path is None:
                return False

            def load() -> dict:
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
                self._workspace.document = document
                return {"document": self._snapshot(include_original=True)}

            return self._run(load)

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

    def _infer(
        self,
        document: ImageDocument,
        preset: str,
        strength: float,
        region: list | str | None,
        device: str,
        announce: bool = True,
    ) -> None:
        from apps.model_library.kokentau.kokentau_v8 import auto_roi, enhance, rectmask

        if preset not in NEURAL_PRESETS | STRUCTURAL_PRESETS:
            raise ValueError("Ferramenta Kokentau desconhecida.")
        if not 0 <= strength <= 1:
            raise ValueError("A intensidade deve estar entre zero e um.")

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
            if (
                not isinstance(region, list)
                or len(region) != 4
                or any(type(item) is not int for item in region)
            ):
                raise ValueError("Região inválida.")
            left, top, right, bottom = region
            if not (0 <= left < right <= pixels.shape[1] and 0 <= top < bottom <= pixels.shape[0]):
                raise ValueError("Selecione uma região dentro da fotografia.")
            mask = rectmask(pixels.shape, region)

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

    def ocre_edit(self, operation: str, value: str | float) -> bool:
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
                        step.apply(Image.new("RGB", (1, 1)))
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
                    document.add(Adjustment(operation, float(value)))
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
                    self._workspace.projects.save(path, document)
                    return {"message": "Projeto salvo."}

                return self._run(save)
            if action != "open":
                raise ValueError("Ação de projeto inválida.")
            path = self._file("Projeto Ocre (*.ocre)")
            if path is None:
                return False

            def load() -> dict:
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
                        if any(
                            getattr(model.manifest, key) != provenance.get(key) for key in hashes
                        ):
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
                state = self._switch_catalog(None)
                self._workspace.document = document
                return {**state, "clear": False, "document": self._snapshot(include_original=True)}

            return self._run(load)

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

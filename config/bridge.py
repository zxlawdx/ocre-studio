"""Native file chooser, editor commands and Vela job completion events."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from time import perf_counter

import numpy as np
from PIL import Image
from vela.core.bridge import BaseBridge
from webview import FileDialog

from apps.editor.service import Adjustment, ImageDocument, histogram, preview
from apps.model_library.service import KokentauModel
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


class EditorBridge(BaseBridge):
    """Expose explicit editor actions while keeping native paths in Python."""

    def __init__(self, router, config, workspace: Workspace) -> None:
        super().__init__(router=router, config=config)
        self._workspace = workspace
        self._state_lock = RLock()
        self._busy = False

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
            "processed": preview(image),
            "histogram": histogram(image),
            "maps": ["original", *document.maps],
            "map": document.selected_map,
            "history": [asdict(step) for step in document.history[: document.cursor]],
            "provenance": document.provenance,
        }
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
            }

    def ocre_open(self) -> bool:
        """Select a photograph in a native file dialog."""
        with self._state_lock:
            path = self._file("Fotografias (*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.webp)")
            if path is None:
                return False

            def load() -> dict:
                self._workspace.document = ImageDocument.open(path)
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

            self.emit("ocre:progress", {"message": "Carregando Kokentau nativo…"})
            registry = self._workspace.native_models

            def execute(requested: str) -> dict:
                nonlocal model
                model = registry.model(requested)
                self.emit(
                    "ocre:progress", {"message": f"Processando em {model.manifest.device.upper()}…"}
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

    def ocre_infer(
        self, preset: str, strength: float, region: list | str | None, device: str
    ) -> bool:
        """Run the selected native preset against the original image."""
        with self._state_lock:
            document = self._document()

            def process() -> dict:
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
                elif operation == "undo":
                    document.cursor = max(0, document.cursor - 1)
                elif operation == "redo":
                    document.cursor = min(len(document.history), document.cursor + 1)
                elif operation == "reset":
                    document.cursor = 0
                    document.selected_map = "original"
                else:
                    document.add(Adjustment(operation, float(value)))
                return {"document": self._snapshot()}

            return self._run(edit)

    def ocre_project(self, action: str) -> bool:
        """Save or reopen a versioned .ocre file through native dialogs."""
        with self._state_lock:
            if action == "save":
                document = self._document()
                path = self._file("Projeto Ocre (*.ocre)", save_as="projeto.ocre")
                if path is None:
                    return False

                def save() -> dict:
                    if path.suffix.lower() != ".ocre":
                        raise ValueError("Use a extensão .ocre no nome do projeto.")
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
                document, provenance, selected = self._workspace.projects.open(path)
                if provenance:
                    hashes = ("grade_sha256", "adaptive_sha256")
                    if any(key in provenance for key in hashes):
                        model = self._workspace.native_models.model("auto")
                        if any(
                            getattr(model.manifest, key) != provenance.get(key) for key in hashes
                        ):
                            raise ValueError("O par nativo não corresponde aos hashes do projeto.")
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
                self._workspace.document = document
                return {"document": self._snapshot(include_original=True)}

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

"""Project smoke check used by the generated Vela frozen launcher."""

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from vela.cli.assets import verify_assets

from apps.editor.service import ImageDocument, histogram
from apps.model_library.kokentau.kokentau_v8 import enhance
from apps.model_library.native import BUNDLED_MODELS, V7_PAYLOAD, NativeModelRegistry
from config.wsgi import create_app


def check(root: Path) -> None:
    """Verify assets, navigation and dependencies inside the frozen process."""
    result = verify_assets(root)
    if not result.ok:
        raise RuntimeError("; ".join(result.errors))
    frozen = getattr(sys, "frozen", False)
    registry = NativeModelRegistry()
    if frozen and registry.directory != root / BUNDLED_MODELS:
        raise RuntimeError(
            "Frozen self-test must use the Kokentau resources beside the executable."
        )
    required = frozen or os.environ.get("OCRE_REQUIRE_NATIVE") == "1"
    if required and not registry.available():
        raise RuntimeError("Native Kokentau weights and metadata are required in this build.")
    if frozen:
        if sys.platform == "win32":
            from webview.platforms.winforms import renderer

            if renderer != "edgechromium":
                raise RuntimeError("WebView2 was not selected in the frozen executable.")
        elif os.environ.get("VELA_GUI") == "gtk":
            from webview.platforms.gtk import renderer

            if renderer != "gtkwebkit2":
                raise RuntimeError("GTK WebKit2 was not selected in the frozen executable.")
    app = create_app()
    try:
        route = app.bridge.navigate("/editor")
        if not route["ok"] or "editor/js/editor.js" not in route["html"]:
            raise RuntimeError("Editor route failed.")
        sample = app.bridge.ocre_state()["document"]
        if not sample or (sample["name"], sample["width"], sample["height"]) != (
            "amostra-inicial.png",
            640,
            420,
        ):
            raise RuntimeError("Startup sample did not load.")
        report = check_inference(app.bridge) if registry.available() else None
    finally:
        app.stop()
    for argument in sys.argv[1:]:
        if argument.startswith("--self-test-report="):
            if report is None:
                raise RuntimeError("The native inference report requires the Kokentau payload.")
            Path(argument.split("=", 1)[1]).write_text(json.dumps(report), encoding="utf-8")


def check_inference(bridge) -> dict:
    """Run the editor's three presets and verify the loaded checkpoint provenance."""
    pixels = np.random.default_rng(42).integers(40, 190, (48, 56, 3), dtype=np.uint8)
    document = ImageDocument(Path("self-test.png"), "", Image.fromarray(pixels))
    classical = enhance(pixels, None)
    report = {}
    for preset in ("adaptativo", "cromatico", "combinado"):
        bridge._infer(document, preset, 0.85, None, "cpu", announce=False)
        image = document.maps[preset]
        provenance = document.provenance
        checkpoints = {
            "grade.pt": provenance.get("grade_sha256"),
            "adaptativo_v7.pt": provenance.get("adaptive_sha256"),
        }
        if checkpoints != V7_PAYLOAD or provenance.get("device") != "cpu":
            raise RuntimeError(f"Verified CPU model provenance missing from {preset}.")
        if (
            image.size != document.original.size
            or sum(histogram(image)[0]) != pixels.shape[0] * pixels.shape[1]
        ):
            raise RuntimeError(f"Invalid inference dimensions or histogram for {preset}.")
        baseline = classical.get(preset, pixels)
        if np.array_equal(np.asarray(image), baseline):
            raise RuntimeError(f"{preset} matches its non-neural baseline.")
        report[preset] = {"device": "cpu", "checkpoints": checkpoints}
    return report

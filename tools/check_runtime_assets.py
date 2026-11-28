"""Project smoke check used by the generated Vela frozen launcher."""

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from vela.cli.assets import verify_assets

from apps.editor.service import histogram
from apps.model_library.kokentau.kokentau_v7_core import AdaptiveV7
from apps.model_library.kokentau.kokentau_v8 import enhance
from apps.model_library.kokentau.legacy import Grade
from apps.model_library.native import NativeModelRegistry
from config.wsgi import create_app


def check(root: Path) -> None:
    """Verify assets, navigation and dependencies inside the frozen process."""
    result = verify_assets(root)
    if not result.ok:
        raise RuntimeError("; ".join(result.errors))
    if getattr(sys, "frozen", False):
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
        pixels = np.random.default_rng(42).integers(40, 190, (48, 56, 3), dtype=np.uint8)
        registry = NativeModelRegistry()
        if registry.available():
            outputs = registry.model("cpu").process(pixels, None, block=64)
        elif os.environ.get("OCRE_REQUIRE_NATIVE") == "1":
            raise RuntimeError("Native Kokentau weights are required in this build.")
        else:
            outputs = enhance(pixels, None, Grade().eval(), AdaptiveV7().eval(), block=64)
        if outputs["combinado"].shape != pixels.shape:
            raise RuntimeError("Synthetic inference result has the wrong dimensions.")
        if sum(histogram(Image.fromarray(outputs["combinado"]))[0]) != 48 * 56:
            raise RuntimeError("Synthetic histogram omitted pixels.")
    finally:
        app.stop()

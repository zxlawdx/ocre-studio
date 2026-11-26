"""Exercise a real Vela WebView with a synthetic image and optional screenshot."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path
from threading import Thread
from time import monotonic, sleep

import numpy as np
from PIL import Image

from config.wsgi import create_app


def wait_for(window, expression: str, timeout: float = 15) -> None:
    """Wait for a particular WebView state."""
    end = monotonic() + timeout
    while monotonic() < end:
        if window.evaluate_js(expression):
            return
        sleep(0.1)
    raise RuntimeError(f"Estado da interface não atingido: {expression}")


def main() -> None:
    """Open the editor, import a generated image, then test the adjustment controls."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--native", action="store_true")
    options = parser.parse_args()
    errors: list[Exception] = []
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "amostra-sintetica.png"
        noise = np.random.default_rng(42).integers(22, 105, (420, 640, 3), dtype=np.uint8)
        noise[100:310, 220:410, 0] += 90
        Image.fromarray(noise).save(source)
        app = create_app()

        def probe() -> None:
            window = None
            try:
                end = monotonic() + 15
                while app.bridge._window is None and monotonic() < end:
                    sleep(0.1)
                window = app.bridge._window
                if window is None or not window.events.loaded.wait(15):
                    raise RuntimeError("A WebView não carregou.")
                app.bridge._file = lambda *_args, **_kwargs: source
                wait_for(window, "Boolean(document.querySelector('.studio-home'))")
                window.evaluate_js("document.querySelector('.studio-home a').click()")
                wait_for(window, "Boolean(document.getElementById('ocre-editor'))")
                sleep(0.4)
                window.evaluate_js("document.querySelector('[data-action=open]').click()")
                wait_for(
                    window,
                    "document.getElementById('filename')?.textContent === 'amostra-sintetica.png'",
                )
                window.evaluate_js(
                    "document.getElementById('adjustment-value').value = 1.3;"
                    "document.querySelector('[data-action=adjust]').click()"
                )
                wait_for(
                    window, "document.querySelector('#history li')?.textContent.includes('1.3')"
                )
                if options.native:
                    window.evaluate_js(
                        "document.getElementById('region').value = 'full';"
                        "document.getElementById('device').value = 'cpu';"
                        "document.querySelector('[data-action=infer]').click()"
                    )
                    wait_for(window, "document.getElementById('maps')?.value === 'combinado'")
                    wait_for(
                        window,
                        "document.getElementById('model-state')?.textContent.includes('CPU')",
                    )
                if options.screenshot:
                    subprocess.run(
                        ["import", "-window", "Ocre Studio", str(options.screenshot)],
                        check=True,
                        timeout=15,
                    )
                print("Smoke GUI aprovado: início, navegação, importação, canvas e ajuste.")
            except Exception as exc:
                errors.append(exc)
            finally:
                if window is not None:
                    window.destroy()

        thread = Thread(target=probe, name="ocre-gui-smoke", daemon=True)
        thread.start()
        app.run()
        thread.join(timeout=2)
    if errors:
        raise RuntimeError("Falha no smoke gráfico.") from errors[0]


if __name__ == "__main__":
    main()

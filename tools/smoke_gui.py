"""Exercise a real Vela WebView with a synthetic image and optional screenshot."""

from __future__ import annotations

import argparse
import os
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


def capture(path: Path) -> None:
    """Capture only the test window."""
    subprocess.run(["import", "-window", "Ocre Studio", str(path)], check=True, timeout=15)


def exercise_workspace(window, saved: Path, screenshot: Path | None) -> None:
    """Exercise folder tabs, ROI, queue, versioned results and project reopen."""

    def click(selector: str) -> None:
        window.evaluate_js(f"document.querySelector({selector!r}).click()")

    def snapshot(label: str) -> None:
        if screenshot:
            capture(screenshot.with_name(f"{screenshot.stem}-{label}{screenshot.suffix}"))

    click('.workspaces [data-panel="projects"]')
    click('[data-screen="projects"] [data-action="new"]')
    wait_for(window, "document.querySelector('#new-project').open")
    snapshot("novo-projeto")
    window.evaluate_js(
        "document.querySelector('#new-project input[name=name]').value = 'Estudo de teste';"
    )
    click('#new-project button[value="confirm"]')
    wait_for(window, "document.querySelector('#project-title').textContent === 'Estudo de teste'")
    snapshot("projetos")
    click('#gallery [data-photo="Painel 01/painel-claro.png"]')
    wait_for(window, "document.querySelector('#filename').textContent === 'painel-claro.png'")
    click('#gallery [data-photo="Painel 01/painel-escuro.png"]')
    wait_for(window, "document.querySelector('#filename').textContent === 'painel-escuro.png'")
    assert window.evaluate_js("document.querySelectorAll('.document-tab').length") == 2
    click('[data-view="roi"]')
    window.evaluate_js("""
        (() => {
            const canvas = document.querySelector('#photograph');
            const rect = canvas.getBoundingClientRect();
            canvas.setPointerCapture = () => {};
            const send = (type, x, y) => canvas.dispatchEvent(new PointerEvent(type, {
                button: 0, pointerId: 1, clientX: rect.left + rect.width * x,
                clientY: rect.top + rect.height * y
            }));
            send('pointerdown', 0.33, 0.30);
            send('pointermove', 0.63, 0.67);
            send('pointerup', 0.63, 0.67);
        })()
    """)
    wait_for(window, "document.querySelector('#region-label').textContent.includes('selecionados')")
    snapshot("roi")
    click('.workspaces [data-panel="batch"]')
    window.evaluate_js("""
        document.querySelector('#batch-form select[name=scope]').value = 'all';
        document.querySelector('#batch-methods input[value=estrutural]').checked = true;
    """)
    click("#start-batch")
    wait_for(window, "document.querySelector('#queue-progress').value === 6", timeout=70)
    assert window.evaluate_js("document.querySelectorAll('#queue [data-batch=open]').length") == 6
    snapshot("lote")
    click("#queue [data-batch=open]")
    wait_for(window, "document.querySelector('#result-list [data-result]') !== null")
    wait_for(window, "document.querySelector('#status').textContent === 'Pronto'")
    snapshot("resultados")
    click('.menubar [data-action="save-project"]')
    wait_for(window, "document.querySelector('#status').textContent === 'Projeto salvo.'")
    assert saved.is_file()
    click('.menubar [data-action="close-project"]')
    wait_for(window, "document.querySelector('#project-heading').textContent === 'Sem projeto'")
    click('.menubar [data-action="open-project"]')
    wait_for(window, "document.querySelector('#project-heading').textContent === 'Estudo de teste'")
    click('#gallery [data-photo="Painel 01/painel-escuro.png"]')
    wait_for(
        window,
        "document.querySelector('#result-list [data-result]') !== null && "
        "document.querySelector('#region-label').textContent.includes('selecionados')",
    )
    if screenshot:
        capture(screenshot)


def main() -> None:
    """Open the editor, import a generated image, then test the adjustment controls."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--workspace", action="store_true")
    parser.add_argument("--size", default="1366x768")
    options = parser.parse_args()
    width, height = map(int, options.size.split("x"))
    errors: list[Exception] = []
    with tempfile.TemporaryDirectory() as folder:
        for variable in ("XDG_DATA_HOME", "LOCALAPPDATA"):
            os.environ[variable] = folder
        source = Path(folder) / "amostra-sintetica.png"
        noise = np.random.default_rng(42).integers(22, 105, (420, 640, 3), dtype=np.uint8)
        noise[100:310, 220:410, 0] += 90
        Image.fromarray(noise).save(source)
        panel = source.parent / "Painel 01"
        panel.mkdir()
        Image.fromarray(255 - noise).save(panel / "painel-claro.png")
        Image.fromarray(noise // 2).save(panel / "painel-escuro.png")
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
                window.resize(width, height)
                saved = source.parent / "estudo.ocre"
                app.bridge._file = lambda description, **_kwargs: (
                    saved if "*.ocre" in description else source
                )
                app.bridge._folder = lambda: source.parent
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
                    "const brightness = document.getElementById('adjust-brightness');"
                    "brightness.value = 1.3; brightness.dispatchEvent(new Event('change', {bubbles: true}));"
                )
                wait_for(
                    window,
                    "document.querySelector('#history li:last-child')?.textContent.includes('Brilho · 1,3')",
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
                        "document.getElementById('dimensions')?.textContent.includes('CPU')",
                    )
                if options.workspace:
                    exercise_workspace(window, saved, options.screenshot)
                elif options.screenshot:
                    capture(options.screenshot)
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

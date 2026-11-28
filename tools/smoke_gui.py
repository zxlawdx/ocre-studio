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
    state = window.evaluate_js("""
        JSON.stringify({status: document.querySelector('#status')?.textContent,
        filename: document.querySelector('#filename')?.textContent,
        busy: document.querySelector('.viewport')?.getAttribute('aria-busy'),
        maps: document.querySelector('#maps')?.value,
        dimensions: document.querySelector('#dimensions')?.textContent})
    """)
    raise RuntimeError(f"Estado da interface não atingido: {expression}; estado: {state}")


def capture(path: Path) -> None:
    """Capture only the test window."""
    subprocess.run(["import", "-window", "Ocre Studio", str(path)], check=True, timeout=15)


def exercise_menus(window) -> None:
    """Switch desktop menus and dismiss them without triggering editor shortcuts."""
    assert window.evaluate_js("""
        (() => {
            const bar = document.querySelector('.menubar');
            const menus = [...bar.querySelectorAll('summary')];
            const count = () => bar.querySelectorAll('details[open]').length;
            const exclusive = menus.every(menu => {
                menu.click();
                return count() === 1 && menu.parentElement.open;
            });
            const last = menus.at(-1);
            window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', cancelable: true}));
            const escaped = count() === 0 && document.activeElement === last;
            menus[0].click();
            document.querySelector('.workspaces').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
            return exclusive && escaped && count() === 0;
        })()
    """)
    assert window.evaluate_js("""
        (() => {
            const bar = document.querySelector('.menubar');
            const menus = [...bar.querySelectorAll('summary')];
            const screens = [...document.querySelectorAll('.workspaces [data-panel]')];
            for (let round = 0; round < 24; round++) {
                for (const menu of menus) {
                    menu.click();
                    if (bar.querySelectorAll('details[open]').length !== 1) return false;
                }
                window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', cancelable: true}));
                for (const screen of screens) {
                    screen.click();
                    const visible = [...document.querySelectorAll('[data-screen]:not([hidden])')];
                    if (visible.length !== 1 || visible[0].dataset.screen !== screen.dataset.panel) return false;
                }
            }
            document.querySelector('.workspaces [data-panel=editor]').click();
            return !bar.querySelector('details[open]');
        })()
    """)


def exercise_histogram(window, screenshot: Path | None) -> None:
    """Check channel geometry and pixel redraw at reduced and default panel widths."""
    window.evaluate_js("document.querySelector('.workspace').style.setProperty('--right', '220px')")
    evidence = window.evaluate_js("""
        (() => {
            const labels = [...document.querySelectorAll('#histogram-channels label')];
            const panel = document.querySelector('.inspector').getBoundingClientRect();
            const bounds = labels.map(label => label.getBoundingClientRect());
            const horizontal = bounds.length === 3 && bounds.every((box, index) =>
                box.top === bounds[0].top && box.right <= panel.right &&
                (index === 0 || bounds[index - 1].right <= box.left));
            const controls = labels.every(label => {
                const box = label.querySelector('input').getBoundingClientRect();
                const text = label.querySelector('span').getBoundingClientRect();
                return box.width === 14 && box.height === 14 && box.right < text.left;
            });
            const inputs = labels.map(label => label.querySelector('input'));
            const canvas = document.getElementById('histogram');
            const original = canvas.toDataURL();
            const independent = inputs.every((input, index) => {
                labels[index].click();
                const changed = !input.checked && inputs.every((other, i) =>
                    i === index || other.checked) && canvas.toDataURL() !== original;
                labels[index].click();
                return changed && input.checked && canvas.toDataURL() === original;
            });
            return { horizontal, controls, independent };
        })()
    """)
    assert evidence == {"horizontal": True, "controls": True, "independent": True}, evidence
    if screenshot:
        capture(screenshot.with_name(f"{screenshot.stem}-histograma{str(screenshot.suffix)}"))
    window.evaluate_js("document.querySelector('.workspace').style.removeProperty('--right')")


def exercise_guide(window, screenshot: Path | None) -> None:
    """Open a credited example through the guide and reproduce its processing."""
    window.evaluate_js("document.querySelector('.workspaces [data-panel=help]').click()")
    wait_for(window, "!document.querySelector('[data-screen=help]').hidden")
    assert window.evaluate_js("""
        (() => {
            const registration = document.querySelector('#guide-tab-field');
            registration.focus();
            registration.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'ArrowRight', bubbles: true, cancelable: true
            }));
            const panel = document.querySelector('#guide-lab');
            const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
            return document.activeElement.id === 'guide-tab-lab' &&
                registration.getAttribute('aria-selected') === 'false' &&
                document.querySelectorAll('.guide [role=tabpanel]:not([hidden])').length === 1 &&
                !panel.hidden && getComputedStyle(panel).animationName ===
                    (reduced ? 'none' : 'workspace-content-enter');
        })()
    """)
    wait_for(
        window,
        """
        Array.from(document.querySelectorAll('#guide-lab img')).slice(0, 2)
            .every(image => image.complete && image.naturalWidth === 1280)
    """,
    )
    if screenshot:
        sleep(0.3)
        capture(screenshot.with_name(f"{screenshot.stem}-guia{screenshot.suffix}"))
    window.evaluate_js("document.querySelector('[data-example=\"serra-da-capivara.jpg\"]').click()")
    wait_for(
        window,
        """
        document.querySelector('#filename').textContent === 'serra-da-capivara.jpg' &&
            !document.querySelector('#tool-classic').disabled &&
            document.querySelector('#status').textContent === 'Pronto'
    """,
    )
    window.evaluate_js("""
        document.querySelector('#tool-classic').click();
        document.querySelector('[data-adjust="decorrelation:1"]').click();
    """)
    wait_for(
        window,
        "document.querySelector('#history li:first-child strong')?.textContent === 'Separar cores' && "
        "document.querySelector('.viewport')?.getAttribute('aria-busy') === 'false'",
    )
    window.evaluate_js("document.querySelector('#tool-enhance').click()")


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
    assert window.evaluate_js("""
        (() => {
            const input = document.querySelector('#new-project .choice-input');
            return input.getBoundingClientRect().right <
                input.nextElementSibling.getBoundingClientRect().left;
        })()
    """)
    snapshot("novo-projeto")
    window.evaluate_js(
        "document.querySelector('#new-project input[name=name]').value = 'Estudo de teste';"
    )
    click('#new-project button[value="confirm"]')
    wait_for(window, "document.querySelector('#project-title').textContent === 'Estudo de teste'")
    snapshot("projetos")
    click("#explorer summary")
    assert window.evaluate_js("""
        (() => {
            const summary = document.querySelector('#explorer summary');
            const [chevron, icon, name] = [...summary.children].map(node =>
                node.getBoundingClientRect());
            return summary.parentElement.open && chevron.right < icon.left &&
                icon.right < name.left && name.right <= summary.getBoundingClientRect().right;
        })()
    """)
    window.evaluate_js("""
        const photo = document.querySelector('#explorer [data-photo="Painel 01/painel-claro.png"]');
        photo.focus();
        photo.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
    """)
    wait_for(
        window,
        "document.querySelector('#filename').textContent === 'painel-claro.png' && "
        "document.querySelector('.viewport').getAttribute('aria-busy') === 'false'",
    )
    click('#gallery [data-photo="Painel 01/painel-escuro.png"]')
    wait_for(
        window,
        "document.querySelector('#filename').textContent === 'painel-escuro.png' && "
        "document.querySelector('.viewport').getAttribute('aria-busy') === 'false'",
    )
    assert window.evaluate_js("document.querySelectorAll('.document-tab').length") == 2
    assert window.evaluate_js("""
        (() => {
            const enhance = document.querySelector('#tool-enhance');
            enhance.focus();
            enhance.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'ArrowRight', bubbles: true, cancelable: true
            }));
            return document.activeElement.id === 'tool-classic' &&
                document.querySelector('#enhance-tools').hidden &&
                document.querySelectorAll('#classic-tools [data-adjust]').length === 15;
        })()
    """)
    if screenshot:
        sleep(0.2)
        snapshot("filtros-classicos")
    click('[data-adjust="equalize:1"]')
    wait_for(
        window,
        "document.querySelector('#history li:first-child')?.textContent.includes('Equalização')",
    )
    click("#tool-enhance")
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
    assert window.evaluate_js("""
        document.querySelector('.viewer .region-toolbar').getBoundingClientRect().height > 0
    """)
    click('[data-view="new-roi"]')
    window.evaluate_js("""
        (() => {
            const canvas = document.querySelector('#photograph');
            const rect = canvas.getBoundingClientRect();
            const send = (type, x, y) => canvas.dispatchEvent(new PointerEvent(type, {
                button: 0, pointerId: 1, clientX: rect.left + rect.width * x,
                clientY: rect.top + rect.height * y
            }));
            send('pointerdown', 0.40, 0.35);
            send('pointermove', 0.49, 0.47);
            send('pointerup', 0.49, 0.47);
        })()
    """)
    assert window.evaluate_js("document.querySelector('#active-region').options.length === 2")
    window.evaluate_js("""
        const region = document.querySelector('#region');
        region.value = 'all';
        region.dispatchEvent(new Event('change', {bubbles: true}));
        document.querySelector('.history-panel').open = true;
    """)
    wait_for(window, "Boolean(document.querySelector('.history-panel > .disclosure-enter'))")
    assert window.evaluate_js("""
        getComputedStyle(document.querySelector('.history-panel > .disclosure-content')).animationName ===
            (matchMedia('(prefers-reduced-motion: reduce)').matches ? 'none' : 'disclosure-expand')
    """)
    click("#tool-classic")
    click('[data-adjust="equalize:1"]')
    wait_for(
        window, "document.querySelector('#history li:first-child span').textContent.includes(' · ')"
    )
    click("#tool-enhance")
    snapshot("roi")
    click(".apply-button")
    wait_for(window, "document.querySelector('#result-list [data-result]') !== null", timeout=45)
    wait_for(window, "document.querySelector('#status').textContent === 'Pronto'")
    assert window.evaluate_js("""
        (() => {
            const provenance = document.querySelector('dl#provenance');
            const labels = [...provenance.querySelectorAll('dt')].map(item => item.textContent);
            return !provenance.hidden && labels.includes('Técnica') &&
                labels.includes('Área') && labels.includes('Duração');
        })()
    """)
    snapshot("realce")
    click('.workspaces [data-panel="batch"]')
    window.evaluate_js("""
        document.querySelector('#batch-form select[name=scope]').value = 'all';
        document.querySelector('#batch-methods input[value=estrutural]').checked = true;
        document.querySelector('.batch-classic').open = true;
        document.querySelector('#batch-classic-methods input[value=classic_equalize_1]').click();
    """)
    assert window.evaluate_js("""
        [...document.querySelectorAll('#batch-methods .choice-input')].every(input =>
            input.getBoundingClientRect().right < input.nextElementSibling.getBoundingClientRect().left)
    """)
    window.evaluate_js("""
        (() => {
            const api = window.pywebview.api;
            const submit = api.ocre_batch;
            window.ocreQaBatchSubmissions = 0;
            api.ocre_batch = (...args) => {
                window.ocreQaBatchSubmissions++;
                return submit(...args);
            };
            const form = document.querySelector('#batch-form');
            document.querySelector('#start-batch').click();
            for (let index = 0; index < 24; index++) {
                form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
            }
        })()
    """)
    wait_for(window, "document.querySelector('#queue-progress').value === 9", timeout=70)
    assert window.evaluate_js("window.ocreQaBatchSubmissions === 1")
    assert window.evaluate_js("document.querySelectorAll('#queue [data-batch=open]').length") == 9
    assert window.evaluate_js("""
        [...document.querySelectorAll('#queue tr')].filter(row =>
            row.cells[1].textContent === 'Equalizar histograma' &&
            row.querySelector('[data-batch=open]')).length === 3
    """)
    click('[data-action="batch-export"]')
    assert window.evaluate_js("""
        [...document.querySelectorAll('#export-results .choice-input')].every(input =>
            input.getBoundingClientRect().right < input.nextElementSibling.getBoundingClientRect().left)
    """)
    click('#export-results button[value="cancel"]')
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
    click('.workspaces [data-panel="projects"]')
    click('[data-screen="projects"] a[href="/recent"]')
    wait_for(window, "Boolean(document.querySelector('#home-projects [data-recent]'))")
    click("#home-projects [data-recent]")
    wait_for(
        window, "document.querySelector('#project-heading')?.textContent === 'Estudo de teste'"
    )
    click('#gallery [data-photo="Painel 01/painel-escuro.png"]')
    wait_for(
        window,
        "document.querySelector('#result-list [data-result]') !== null && "
        "document.querySelector('#active-region').options.length === 2",
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
                if window is None or not window.events.loaded.wait(45):
                    raise RuntimeError("A WebView não carregou.")
                window.resize(width, height)
                if width >= 1920 and height >= 1080 and options.screenshot:
                    window.toggle_fullscreen()
                saved = source.parent / "estudo.ocre"
                app.bridge._file = lambda description, **_kwargs: (
                    saved if "*.ocre" in description else source
                )
                app.bridge._folder = lambda: source.parent
                wait_for(window, "Boolean(document.querySelector('.studio-home, #ocre-editor'))")
                if options.screenshot and window.evaluate_js(
                    "Boolean(document.querySelector('.studio-home'))"
                ):
                    sleep(0.2)
                    capture(options.screenshot.with_name(f"{options.screenshot.stem}-inicio.png"))
                window.evaluate_js(
                    "document.querySelector('.studio-home .home-actions a[href=\"/editor\"]')?.click()"
                )
                wait_for(
                    window,
                    "document.getElementById('filename')?.textContent === 'amostra-inicial.png' && "
                    "document.getElementById('placeholder').hidden && "
                    "document.querySelector('.viewport')?.getAttribute('aria-busy') === 'false'",
                )
                sleep(0.4)
                exercise_menus(window)
                exercise_guide(window, options.screenshot)
                window.evaluate_js("document.querySelector('[data-action=open]').click()")
                wait_for(
                    window,
                    "document.getElementById('filename')?.textContent === 'amostra-sintetica.png' && "
                    "document.querySelector('.viewport')?.getAttribute('aria-busy') === 'false'",
                )
                window.evaluate_js(
                    "const brightness = document.getElementById('adjust-brightness');"
                    "brightness.value = 1.3; brightness.dispatchEvent(new Event('change', {bubbles: true}));"
                )
                wait_for(
                    window,
                    "document.querySelector('#history li:first-child strong')?.textContent === 'Brilho' && "
                    "document.querySelector('#history li:first-child span')?.textContent === '1,3'",
                )
                if options.native:
                    wait_for(window, "document.querySelector('.apply-button')?.disabled === false")
                    print(window.evaluate_js("document.querySelector('#model-state').textContent"))
                    window.evaluate_js(
                        "document.getElementById('region').value = 'full';"
                        "document.getElementById('device').value = 'cpu';"
                        "document.querySelector('.apply-button').click()"
                    )
                    wait_for(
                        window,
                        "document.getElementById('maps')?.value === 'combinado'",
                        timeout=180,
                    )
                    wait_for(
                        window,
                        "document.getElementById('dimensions')?.textContent.includes('CPU')",
                        timeout=180,
                    )
                exercise_histogram(window, options.screenshot)
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

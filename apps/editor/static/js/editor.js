import { BatchView } from "./batch.js";
import { CatalogView } from "./catalog.js";
import { mountDisclosures } from "./disclosures.js";
import { describeArea, filterName, renderHistory } from "./history.js";
import { mountMenubar } from "./menubar.js";
import { adjustments, classicFilters, element, intensity, neural, techniqueName, techniques } from "./techniques.js";
import { mountTabs } from "./tabs.js";
import { Viewport } from "./viewport.js";

function drawHistogram(canvas, channels, visible) {
    const ctx = canvas.getContext("2d");
    const style = getComputedStyle(canvas);
    const colors = ["red", "green", "blue"].map((channel) =>
        style.getPropertyValue(`--channel-${channel}`).trim()
    );
    const maximum = Math.max(1, ...channels.flat());
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    channels.forEach((channel, index) => {
        if (!visible.has(index)) return;
        ctx.beginPath();
        ctx.strokeStyle = colors[index];
        channel.forEach((count, bin) => {
            const x = bin * (canvas.width - 1) / 255;
            const y = canvas.height - 2 - Math.sqrt(count / maximum) * (canvas.height - 4);
            if (bin === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
    });
}

function initializeTools(find, adjust, signal) {
    Object.entries(techniques).forEach(([key, [title, help]], index) => {
        const label = element("label", "", { title: help });
        const radio = element("input", "", { type: "radio", name: "technique", value: key });
        radio.checked = key === "combinado";
        label.append(radio, document.createTextNode(title));
        find(index < 4 ? "#primary-techniques" : "#structural-techniques").append(label);
    });
    for (const [key, [title, min, max, step]] of Object.entries(adjustments).slice(0, 5)) {
        const row = element("div", "", { class: "adjustment" });
        const range = element("input", "", { type: "range", min, max, step, id: `adjust-${key}`, "data-document": "" });
        const number = element("input", "", { type: "number", min, max, step, "aria-label": title, "data-document": "" });
        range.value = number.value = 1;
        row.append(element("label", title, { for: range.id, title: "O valor 1 mantém a imagem sem alteração." }), range, number);
        range.addEventListener("input", () => { number.value = range.value; }, { signal });
        for (const control of [range, number]) {
            control.addEventListener("change", () => {
                const value = control.valueAsNumber;
                if (!Number.isFinite(value) || value < min || value > max) {
                    number.value = range.value;
                    return;
                }
                range.value = number.value = value;
                adjust(key, value);
            }, { signal });
        }
        find("#adjustments").append(row);
    }
}

function initializeResize(root, signal) {
    for (const splitter of root.querySelectorAll("[data-resize]")) {
        const side = splitter.dataset.resize;
        const minimum = Number(splitter.getAttribute("aria-valuemin"));
        let start;
        const apply = (value) => {
            const limit = Math.min(Number(splitter.getAttribute("aria-valuemax")), root.clientWidth * 0.38);
            const width = Math.round(Math.max(minimum, Math.min(limit, value)));
            root.style.setProperty(`--${side}`, `${width}px`);
            splitter.setAttribute("aria-valuenow", width);
        };
        splitter.addEventListener("pointerdown", (event) => {
            splitter.setPointerCapture(event.pointerId);
            start = [event.clientX, splitter.previousElementSibling?.clientWidth];
            if (side === "right") start[1] = Number.parseFloat(getComputedStyle(root).getPropertyValue("--right"));
        }, { signal });
        splitter.addEventListener("pointermove", (event) => {
            if (splitter.hasPointerCapture(event.pointerId) && start) {
                apply(start[1] + (event.clientX - start[0]) * (side === "left" ? 1 : -1));
            }
        }, { signal });
        splitter.addEventListener("keydown", (event) => {
            if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
            event.preventDefault();
            apply(Number.parseFloat(getComputedStyle(root).getPropertyValue(`--${side}`)) +
                (event.key === "ArrowRight" ? 12 : -12) * (side === "left" ? 1 : -1));
        }, { signal });
    }
}

export async function mount(root, signal) {
    const find = (selector) => root.querySelector(selector);
    const api = window.pywebview.api;
    const report = (message) => { find("#status").textContent = message; };
    const viewport = new Viewport(find("#photograph"), (percent) => {
        find("#scale").textContent = `Zoom ${percent}%`;
        find("#comparison").value = Math.round(viewport.divider * 100);
    }, signal);
    let loaded = false;
    let busy = false;
    let revision = 0;
    let nativeAvailable = false;
    let documentState = null;
    const processing = new Set();
    let clipboard = [];
    let afterOpen = null;
    let activePanel = "editor";
    const method = () => find('[name="technique"]:checked')?.value ?? "combinado";
    const strength = () => Number(find("#strength").value);
    const catalog = new CatalogView(root, api, signal, openPhoto);
    const batch = new BatchView(root, catalog, api, signal, report, (task) => {
        if (busy) return;
        if (catalog.photo === task.photo) void command(() => api.ocre_result(task.result, "open"));
        else {
            afterOpen = task.result;
            openPhoto(task.photo);
        }
    }, saveView);

    function updateRegion() {
        const roi = viewport.roi;
        const regions = viewport.regions;
        const mode = find("#region").value;
        const label = mode === "all" && regions.length ? `${regions.length} regiões` :
            mode === "selection" && roi ? `R${viewport.activeRegion + 1} · ${roi[2] - roi[0]} × ${roi[3] - roi[1]} px selecionados` :
                describeArea({ auto: "auto", saved: "saved" }[mode]);
        find("#region-label").textContent = `Área · ${label}`;
        const selector = find("#active-region");
        const options = regions.map((box, index) =>
            new Option(`R${index + 1} · ${box[2] - box[0]} × ${box[3] - box[1]} px`, index));
        selector.replaceChildren(...(options.length ? options : [new Option("Nenhuma", "")]));
        if (options.length) selector.value = String(viewport.activeRegion);
        selector.disabled = !options.length || busy;
        find('[data-view="clear-roi"]').disabled = !roi || busy;
    }

    function selectedRegions() {
        return { selection: viewport.roi ? [viewport.roi] : [], all: viewport.regions }[find("#region").value] ?? [];
    }

    function viewState() {
        return {
            zoom: viewport.zoom, pan: viewport.pan, mode: viewport.mode,
            divider: viewport.divider, comparison: viewport.comparison,
            technique: method(), strength: strength(), region: find("#region").value,
            adjustments: docAdjustments()
        };
    }

    async function saveView() {
        if (loaded) await api.ocre_view(catalog.photo, viewport.regions, viewport.activeRegion, viewState());
    }

    viewport.onRegionLimit = () => report("Use até 16 regiões por fotografia.");
    viewport.onRegion = () => {
        if (find("#region").value !== "all") find("#region").value = "selection";
        updateRegion();
        if (catalog.catalog) catalog.catalog.dirty = true;
        controls();
        void saveView().catch((error) => report(error.message));
    };

    function panel(name) {
        activePanel = name;
        root.dataset.workspace = name;
        root.querySelectorAll("[data-screen]").forEach((node) => { node.hidden = node.dataset.screen !== name; });
        root.querySelectorAll(".workspaces [data-panel]").forEach((node) => {
            if (node.dataset.panel === name) node.setAttribute("aria-current", "page");
            else node.removeAttribute("aria-current");
        });
        controls();
        if (name === "editor") viewport.draw();
    }

    function controls() {
        root.querySelectorAll("[data-document]").forEach((node) => { node.disabled = !loaded || busy; });
        find(".viewport").setAttribute("aria-busy", String(busy || processing.has(catalog.photo)));
        find("#device").disabled = !neural.has(method()) || busy;
        find("#strength").disabled = !intensity.has(method()) || busy;
        find("#strength-value").textContent = `${Math.round(strength() * 100)}%`;
        root.querySelectorAll('[data-action="infer"]').forEach((node) => {
            node.disabled = !loaded || busy || processing.has(catalog.photo) ||
                (neural.has(method()) && !nativeAvailable);
        });
        for (const node of root.querySelectorAll('[data-action="save-project"],[data-action="save-as"]')) {
            node.disabled = busy || (!catalog.catalog && !loaded);
        }
        for (const node of root.querySelectorAll('[data-action="close-project"],[data-action="save-preset"]')) {
            node.disabled = busy || !catalog.catalog;
        }
        find("#cancel-photo").hidden = !processing.has(catalog.photo);
        const project = catalog.catalog;
        find("#project-status").textContent = project ?
            `${project.name} · ${project.dirty ? "Alterações não salvas" : "Projeto salvo"}` : "Sem projeto";
        updateRegion();
    }

    function clearDocument() {
        documentState = null;
        loaded = false;
        viewport.images = [];
        viewport.regions = [];
        viewport.activeRegion = 0;
        viewport.draw();
        find("#placeholder").hidden = false;
        find("#comparison-bar").hidden = true;
        find("#filename").textContent = "Galeria";
        find("#dimensions").textContent = "";
        find("#scale").textContent = "—";
        find("#history").replaceChildren();
        find("#result-list").replaceChildren();
        find("#maps").replaceChildren(new Option("Original", "original"));
        showProvenance(null);
        drawHistogram(find("#histogram"), [], new Set());
    }

    function presentResults(results) {
        find("#result-list").replaceChildren(...results.map((entry) => {
            const row = element("div", "", { class: "result-item" });
            const title = entry.name || techniqueName(entry.technique);
            row.append(
                element("button", title, { "data-result": entry.id, "data-result-action": "open", title: `Abrir ${title}` }),
                element("button", entry.favorite ? "★" : "☆", { "data-result": entry.id, "data-result-action": "favorite", "aria-label": `Favorito: ${title}` }),
                element("button", "Comparar", { "data-result": entry.id, "data-result-action": "compare" }),
                element("button", "Renomear", { "data-result": entry.id, "data-result-action": "rename" }),
                element("small", new Date(entry.created).toLocaleString("pt-BR"))
            );
            return row;
        }));
    }

    function plots() {
        const selected = new Set([...root.querySelectorAll("#histogram-channels input:checked")].map((input) => Number(input.value)));
        drawHistogram(find("#histogram"), documentState?.histogram ?? [], selected);
    }

    function showProvenance(provenance) {
        const list = find("#provenance");
        list.replaceChildren();
        if (!provenance?.preset) {
            list.hidden = true;
            return;
        }
        const { preset, roi, device, seconds } = provenance;
        const entries = [
            ["Técnica", techniqueName(preset)],
            ["Área", describeArea(roi)],
            ["Dispositivo", device?.toUpperCase()],
            ["Duração", Number.isFinite(seconds) ? `${seconds.toLocaleString("pt-BR", {
                maximumFractionDigits: 2
            })} s` : null]
        ];
        for (const [name, value] of entries) {
            if (value) list.append(element("dt", name), element("dd", value));
        }
        list.hidden = false;
    }

    async function present(value) {
        if (typeof value.native_available === "boolean") {
            nativeAvailable = value.native_available;
            find("#model-state").textContent = nativeAvailable ? "Modelos disponíveis" : "Recursos de realce cromático ausentes.";
        }
        if ("catalog" in value) {
            catalog.apply(value.catalog);
            const presets = Object.keys(value.catalog?.presets ?? {});
            find("#presets").replaceChildren(new Option("Escolher preset", ""), ...presets.map((name) => new Option(name, name)));
            find("#batch-preset").replaceChildren(new Option("Configuração manual", ""), ...presets.map((name) => new Option(name, name)));
        }
        if (value.queue) batch.render(value.queue);
        if (value.clear) clearDocument();
        if (value.screen) panel(value.screen);
        if (value.comparison) {
            if (value.comparison_size[0] !== documentState.width || value.comparison_size[1] !== documentState.height) {
                throw new Error("Os resultados têm resoluções diferentes. Abra cada resultado separadamente.");
            }
            const image = new Image();
            image.src = value.comparison;
            await image.decode();
            viewport.images[0] = image;
            find("#before-label").textContent = "Segundo resultado";
            viewport.draw();
        }
        const doc = value.document;
        if (!doc) return;
        documentState = doc;
        loaded = true;
        catalog.activate(doc.photo ?? null);
        if (catalog.catalog && typeof doc.dirty === "boolean") catalog.catalog.dirty = doc.dirty;
        find("#placeholder").hidden = true;
        find("#comparison-bar").hidden = false;
        find("#filename").textContent = doc.name;
        const { seconds, device } = doc.provenance;
        find("#dimensions").textContent = [`${doc.width} × ${doc.height} px`, device?.toUpperCase(),
            seconds === undefined ? "" : `${seconds.toFixed(2)} s`].filter(Boolean).join(" · ");
        showProvenance(doc.map === "original" ? null : doc.provenance);
        if (doc.original) {
            find("#before-label").textContent = "Original";
            const stored = doc.view ?? {};
            const radio = [...root.querySelectorAll('[name="technique"]')].find((input) => input.value === stored.technique);
            if (radio) radio.checked = true;
            find("#strength").value = stored.strength ?? 0.85;
            find("#region").value = stored.region ?? "selection";
            viewport.mode = stored.mode ?? "pan";
            viewport.divider = stored.divider ?? 0.5;
            viewport.comparison = stored.comparison ?? "wipe";
            controlView();
        }
        const results = doc.results ?? [];
        find("#maps").replaceChildren(...doc.maps.map((name) => {
            const entry = results.find((item) => item.id === name);
            return new Option(entry?.name || techniqueName(entry?.technique ?? name), name);
        }));
        find("#maps").value = doc.map;
        presentResults(results);
        renderHistory(find("#history"), doc);
        for (const key of Object.keys(adjustments).slice(0, 5)) {
            const current = [...doc.history].reverse().find((step) => step.name === key);
            const range = find(`#adjust-${key}`);
            range.value = current?.value ?? 1;
            range.nextElementSibling.value = range.value;
        }
        plots();
        const matchingSize = doc.width === (doc.original_width ?? doc.width) &&
            doc.height === (doc.original_height ?? doc.height);
        if (!matchingSize) {
            viewport.comparison = "result";
            find("#comparison-bar").hidden = true;
        }
        await viewport.load(doc, signal);
        if (doc.original && !signal.aborted) {
            const canvas = find("#photograph");
            canvas.classList.remove("photo-enter");
            void canvas.offsetWidth;
            canvas.classList.add("photo-enter");
        }
    }

    async function command(callback, message = "Em andamento…") {
        if (busy) return;
        busy = true;
        const sent = ++revision;
        controls();
        report(message);
        try {
            if (await callback()) return;
            if (sent === revision) report("Pronto");
        } catch (error) {
            afterOpen = null;
            if (sent === revision) report(error.message);
        }
        if (sent === revision) {
            busy = false;
            controls();
        }
    }

    function openPhoto(key) {
        if (busy) return;
        panel("editor");
        void command(async () => {
            await saveView();
            return api.ocre_photo(key);
        });
    }

    function closeTab(key) {
        if (busy || !key) return;
        const index = catalog.tabs.indexOf(key);
        catalog.tabs = catalog.tabs.filter((item) => item !== key);
        if (key === catalog.photo) {
            if (catalog.tabs.length) openPhoto(catalog.tabs[Math.min(index, catalog.tabs.length - 1)]);
            else {
                void saveView().catch((error) => report(error.message));
                catalog.activate(null);
                clearDocument();
            }
        }
        catalog.renderTabs();
        controls();
    }

    function controlView() {
        root.querySelectorAll("[data-comparison]").forEach((item) => item.setAttribute("aria-pressed", String(item.dataset.comparison === viewport.comparison)));
        for (const mode of ["roi", "pan"]) {
            find(`[data-view="${mode}"]`).setAttribute("aria-pressed", String(mode === viewport.mode));
        }
        find("#photograph").style.cursor = viewport.mode === "roi" ? "crosshair" : "grab";
    }

    function view(action) {
        if (action === "fit") viewport.fit();
        if (action === "actual" && viewport.images.length) {
            viewport.changeZoom(viewport.dimensions[0] / viewport.images[0].width / viewport.zoom);
        }
        if (action === "out") viewport.changeZoom(1 / 1.2);
        if (action === "in") viewport.changeZoom(1.2);
        if (action === "clear-roi") viewport.cancel();
        if (action === "new-roi") {
            viewport.addRegion = true;
            report("Arraste sobre a imagem para desenhar uma região.");
        } else if (action === "pan" || action === "clear-roi") viewport.addRegion = false;
        if (["roi", "new-roi", "pan"].includes(action)) viewport.mode = action === "new-roi" ? "roi" : action;
        if (viewport.mode === "roi" && viewport.comparison === "side") viewport.comparison = "wipe";
        viewport.draw();
        controlView();
    }

    const sync = (callback) => { void command(callback); };
    const edit = (operation, value) => sync(() => api.ocre_edit(operation, value, null));
    function canLeave() {
        return !catalog.catalog?.dirty || window.confirm("O projeto contém alterações não salvas. Continuar?");
    }

    async function preset(remove) {
        if (!catalog.catalog) throw new Error("Abra um projeto para guardar presets.");
        const name = remove ? find("#presets").value : window.prompt("Nome do preset");
        if (!name || (remove && !window.confirm(`Remover o preset ${name}?`))) return false;
        const summary = await api.ocre_preset(name, remove ? null : {
            technique: method(), strength: strength(), region: find("#region").value,
            adjustments: docAdjustments().filter((step) => !step.regions?.length)
        });
        await present({ catalog: summary });
        return false;
    }

    const docAdjustments = () => documentState?.history ?? [];
    function exportBatch() {
        const dialog = find("#export-results");
        dialog.returnValue = "";
        dialog.showModal();
    }
    const actions = {
        open: () => { panel("editor"); return command(() => api.ocre_open()); },
        folder: () => { if (canLeave()) sync(() => api.ocre_folder(true)); },
        new: () => { if (canLeave()) { find("#new-project").returnValue = ""; find("#new-project").showModal(); } },
        help: () => panel("help"),
        "practice-project": () => {
            if (canLeave()) sync(() => api.ocre_practice_project());
        },
        infer: () => {
            const mode = find("#region").value;
            const regions = selectedRegions();
            const region = { saved: "saved", auto: "auto" }[mode] ?? (regions.length ? regions : null);
            const run = () => api.ocre_infer(method(), strength(), region, find("#device").value);
            const photo = catalog.photo;
            if (!photo) { sync(run); return; }
            if (processing.has(photo) || busy) return;
            processing.add(photo);
            catalog.statuses.set(photo, "Processando");
            catalog.update();
            controls();
            report(`Processando ${documentState.name}…`);
            void saveView().then(run).catch((error) => {
                processing.delete(photo);
                catalog.statuses.set(photo, "Falha");
                catalog.update();
                report(error.message);
                controls();
            });
        },
        "cancel-photo": () => {
            void api.ocre_cancel_photo(catalog.photo).then((accepted) => {
                if (accepted) report("Cancelando após o cálculo atual…");
            }).catch((error) => report(error.message));
        },
        undo: () => edit("undo", 0),
        redo: () => edit("redo", 0),
        reset: () => edit("reset", 0),
        export: () => sync(() => api.ocre_export()),
        "open-project": () => { if (canLeave()) sync(() => api.ocre_project("open")); },
        "save-project": () => sync(async () => { await saveView(); await api.ocre_tabs(catalog.tabs); return api.ocre_project("save"); }),
        "save-as": () => sync(async () => { await saveView(); await api.ocre_tabs(catalog.tabs); return api.ocre_project("save-as"); }),
        "close-project": () => { if (canLeave()) sync(() => api.ocre_catalog_action("close")); },
        refresh: () => sync(() => api.ocre_catalog_action("refresh")),
        destination: () => sync(() => api.ocre_catalog_action("destination")),
        "copy-adjustments": () => { clipboard = documentState?.history ?? []; report("Ajustes copiados."); },
        "paste-adjustments": () => { if (clipboard.length) edit("paste", clipboard); },
        "close-tab": () => closeTab(catalog.photo),
        "close-others": () => { catalog.tabs = catalog.photo ? [catalog.photo] : []; catalog.renderTabs(); },
        "save-preset": () => sync(() => preset(false)),
        "remove-preset": () => sync(() => preset(true)),
        "import-preset": () => sync(() => api.ocre_preset_file("import")),
        "export-preset": () => sync(() => api.ocre_preset_file("export", find("#presets").value)),
        "paste-preset": () => {
            const values = catalog.catalog?.presets[find("#presets").value]?.adjustments;
            if (values?.length) edit("paste", values);
        },
        "batch-export": exportBatch,
        "context-open": () => openPhoto(catalog.context),
        "context-batch": () => { catalog.selected.add(catalog.context); catalog.update(); panel("batch"); },
        "context-results": () => openPhoto(catalog.context),
        "toggle-explorer": () => root.classList.toggle("hide-explorer"),
        "toggle-inspector": () => root.classList.toggle("hide-inspector"),
        "toggle-gallery": () => root.classList.toggle("hide-gallery")
    };

    mountDisclosures(root, signal);
    mountTabs(root, find(".tool-tabs"), signal);
    mountTabs(root, find(".guide-nav"), signal, () => {
        find(".help-page").scrollTop = 0;
    });
    initializeTools(find, (operation, value) => edit(`set:${operation}`, value), signal);
    initializeResize(root, signal);
    mountMenubar(find(".menubar"), signal);
    root.addEventListener("click", (event) => {
        const trigger = event.target.closest("button");
        if (!trigger || trigger.disabled) return;
        const { action, panel: screen, view: tool, comparison, result, resultAction, adjust, history, tab, closeTab: tabToClose } = trigger.dataset;
        if (action) actions[action]?.();
        if (trigger.dataset.recent && canLeave()) sync(() => api.ocre_open_recent(trigger.dataset.recent));
        if (trigger.dataset.recentRemove) sync(() => api.ocre_open_recent(trigger.dataset.recentRemove, true));
        if (screen) panel(screen);
        if (trigger.dataset.example && !busy) {
            panel("editor");
            void command(() => api.ocre_open_example(trigger.dataset.example), "Abrindo fotografia do exercício…");
        }
        if (tool) view(tool);
        if (comparison) {
            viewport.comparison = comparison;
            controlView();
            if (comparison === "side") {
                viewport.mode = "pan";
                viewport.fit();
                controlView();
            } else viewport.draw();
            find("#comparison-bar").hidden = !["wipe", "overlay"].includes(comparison);
        }
        if (adjust) {
            const [operation, amount] = adjust.split(":");
            const mode = find("#region").value;
            if (["auto", "saved"].includes(mode)) {
                report("Para este filtro, escolha uma região desenhada ou a imagem inteira.");
                return;
            }
            const areas = selectedRegions();
            const previous = documentState.history.at(-1);
            const input = previous ? filterName(previous.name, previous.value) :
                techniqueName(documentState.map === "original" ? "original" : documentState.provenance.preset);
            void command(() => api.ocre_edit(operation, Number(amount), areas),
                `Aplicando ${filterName(operation, Number(amount))} · entrada: ${input}…`);
        }
        if (history) edit("history", Number(history));
        if (tab !== undefined) openPhoto(tab);
        if (tabToClose !== undefined) closeTab(tabToClose);
        if (result) {
            const name = resultAction === "rename" ? window.prompt("Nome do resultado") : "";
            if (name !== null) sync(() => api.ocre_result(result, resultAction, name));
        }
        if (trigger.closest("#catalog-context")) find("#catalog-context").hidden = true;
    }, { signal });

    find("#new-project").addEventListener("close", (event) => {
        if (event.target.returnValue !== "confirm") return;
        const fields = new FormData(event.target.querySelector("form"));
        sync(() => api.ocre_folder(fields.has("recursive"), Object.fromEntries(fields)));
    }, { signal });
    for (const name of ["change", "input"]) {
        find(".inspector").addEventListener(name, controls, { signal });
    }
    find("#export-results").addEventListener("close", (event) => {
        if (event.target.returnValue !== "confirm") return;
        const data = new FormData(event.target.querySelector("form"));
        const scope = data.get("scope");
        const keys = scope === "all" ? catalog.catalog?.photos ?? [] :
            scope === "current" ? [catalog.photo].filter(Boolean) : [...catalog.selected];
        sync(() => api.ocre_export_results(keys, {
            format: data.get("format"), technique: data.get("technique"),
            max_side: Number(data.get("max_side")), quality: Number(data.get("quality")),
            favorite: data.has("favorite"), metadata: data.has("metadata")
        }));
    }, { signal });
    for (const [key] of Object.entries({ ...techniques, ...classicFilters })) {
        find('#export-results select[name="technique"]').append(new Option(techniqueName(key), key));
    }
    find("#presets").addEventListener("change", (event) => {
        const value = catalog.catalog?.presets[event.target.value];
        if (!value) return;
        const radio = [...root.querySelectorAll('[name="technique"]')].find((input) => input.value === value.technique);
        if (radio) radio.checked = true;
        find("#strength").value = value.strength;
        find("#region").value = value.region;
        controls();
    }, { signal });
    find("#technical-details").addEventListener("toggle", async (event) => {
        if (!event.target.open) return;
        try {
            const { cuda } = await api.ocre_devices();
            const option = find('#device option[value="cuda"]');
            option.disabled = !cuda;
            option.textContent = cuda ? "CUDA" : "CUDA indisponível";
        } catch (error) {
            report(error.message);
        }
    }, { signal });
    find("#active-region").addEventListener("change", (event) =>
        viewport.selectRegion(Number(event.target.value)), { signal });
    find("#region").addEventListener("change", () => {
        updateRegion();
        void saveView().catch((error) => report(error.message));
    }, { signal });
    find("#histogram-channels").addEventListener("change", plots, { signal });
    find("#comparison").addEventListener("input", (event) => {
        viewport.divider = Number(event.target.value) / 100;
        viewport.draw();
    }, { signal });
    find("#maps").addEventListener("change", (event) => edit("map", event.target.value), { signal });

    window.addEventListener("keydown", (event) => {
        if (event.target.closest?.("input, textarea, select, dialog, [contenteditable]")) return;
        const key = event.key.toLowerCase();
        const modifier = event.ctrlKey || event.metaKey;
        const shortcuts = {
            n: "new", o: event.shiftKey ? "folder" : "open",
            s: event.shiftKey ? "save-as" : "save-project",
            z: event.shiftKey ? "redo" : "undo", y: "redo", w: "close-tab"
        };
        if (modifier && key === "tab" && catalog.tabs.length > 1) {
            event.preventDefault();
            openPhoto(catalog.tabs[(catalog.tabs.indexOf(catalog.photo) + 1) % catalog.tabs.length]);
        } else if (modifier && shortcuts[key]) {
            event.preventDefault();
            actions[shortcuts[key]]();
        } else if (!modifier && activePanel === "editor" && !event.defaultPrevented) {
            const tools = { r: "roi", m: "pan", escape: "clear-roi", "0": "fit", "+": "in", "-": "out" };
            if (tools[key]) { event.preventDefault(); view(tools[key]); }
        }
    }, { signal });

    window.addEventListener("vela:event", async (event) => {
        const { name, payload } = event.detail;
        if (name === "ocre:progress") report(payload.message);
        if (name === "ocre:batch") batch.render(payload);
        if (name === "ocre:photo-processing") {
            if (payload.catalog !== catalog.catalog?.root) return;
            processing.delete(payload.photo);
            catalog.statuses.set(payload.photo, ({ done: "Processada", cancelled: "Cancelada", failed: "Falha" })[payload.state]);
            if (payload.state === "done") catalog.catalog.dirty = true;
            catalog.update();
            controls();
            if (catalog.photo === payload.photo) {
                if (payload.id && !busy) sync(() => api.ocre_result(payload.id, "open"));
                else report(payload.message ?? (payload.id ? "Resultado disponível." : "Processamento cancelado."));
            }
        }
        if (name !== "ocre:result") return;
        ++revision;
        const { error, result } = payload;
        try {
            if (result) await present(result);
            report(error || result?.message || "Pronto");
        } catch (problem) {
            report(problem.message || "Falha ao exibir a fotografia.");
        } finally {
            busy = false;
            controls();
            const pending = afterOpen;
            afterOpen = null;
            if (pending && result?.document && !error) void command(() => api.ocre_result(pending, "open"));
        }
    }, { signal });

    controls();
    try {
        const [state, queue] = await Promise.all([api.ocre_state(), api.ocre_batch_state()]);
        if (signal.aborted) return;
        busy = Boolean(state.busy);
        await present(state);
        batch.render(queue);
        if (state.catalog && !state.document) panel("projects");
    } catch {
        report("Falha ao recuperar o estado do editor.");
    }
    controls();
}

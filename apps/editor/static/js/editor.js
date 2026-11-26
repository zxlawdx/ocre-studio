import { Viewport } from "./viewport.js";

function drawHistogram(canvas, channels) {
    const ctx = canvas.getContext("2d");
    const colors = ["#f48a7f", "#8dd9a0", "#8caef4"];
    const maximum = Math.max(1, ...channels.flat());
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    channels.forEach((channel, index) => {
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

export async function mount(root, signal) {
    const find = (selector) => root.querySelector(selector);
    const api = window.pywebview.api;
    const status = find("#status");
    const viewport = new Viewport(find("#photograph"), (percent) => {
        find("#scale").textContent = `${percent}% da prévia`;
    }, signal);
    let loaded = false;
    let busy = false;
    let revision = 0;
    let nativeAvailable = false;
    const neuralPresets = new Set(["adaptativo", "cromatico", "combinado"]);

    function controls() {
        root.querySelectorAll("[data-document]").forEach((node) => {
            node.disabled = !loaded || busy;
        });
        const preset = find("#preset").value;
        find("#device").disabled = !neuralPresets.has(preset) || busy;
        find("#strength").disabled = !["cromatico", "combinado"].includes(preset) || busy;
        find("[data-action=infer]").disabled = !loaded || busy ||
            (neuralPresets.has(preset) && !nativeAvailable);
        for (const node of root.querySelectorAll("[data-action]:not([data-document])")) {
            node.disabled = busy;
        }
    }

    async function present(value) {
        if (typeof value.native_available === "boolean") {
            nativeAvailable = value.native_available;
            find("#model-state").textContent = nativeAvailable
                ? "Grade + AdaptiveV7 · pronto para carregar"
                : "Recursos neurais nativos ausentes nesta distribuição.";
        }
        const document = value.document;
        if (!document) return;
        loaded = true;
        find("#placeholder").hidden = true;
        find("#empty-library").hidden = true;
        find("#source-card").hidden = false;
        find("#filename").textContent = document.name;
        const timing = document.provenance.seconds;
        if (document.provenance.architecture) {
            const { architecture, device, epoch } = document.provenance;
            find("#model-state").textContent = `${architecture} · época ${epoch} · ${device.toUpperCase()}`;
        }
        find("#dimensions").textContent = `${document.width} × ${document.height} px` +
            (timing === undefined ? "" : ` · ${timing.toFixed(2)} s`);
        if (document.original) find("#thumbnail").src = document.original;
        find("#maps").replaceChildren(...document.maps.map((name) => new Option(name, name)));
        find("#maps").value = document.map;
        find("#history").replaceChildren(...document.history.map((step) => {
            const item = window.document.createElement("li");
            item.textContent = `${step.name} · ${step.value}`;
            return item;
        }));
        drawHistogram(find("#histogram"), document.histogram);
        await viewport.load(document, signal);
    }

    async function command(callback) {
        if (busy) return;
        busy = true;
        const sent = ++revision;
        controls();
        status.textContent = "Em andamento…";
        try {
            if (await callback()) return;
            if (sent === revision) status.textContent = "Pronto";
        } catch (error) {
            if (sent === revision) status.textContent = error.message;
        }
        if (sent === revision) {
            busy = false;
            controls();
        }
    }

    const actions = {
        open: () => api.ocre_open(),
        infer: () => {
            const mode = find("#region").value;
            if (mode === "selection" && !viewport.roi) {
                throw new Error("Selecione uma ROI ou escolha Fotografia inteira.");
            }
            const region = { selection: viewport.roi, full: null, saved: "saved", auto: "auto" }[mode];
            return api.ocre_infer(
                find("#preset").value, Number(find("#strength").value), region, find("#device").value
            );
        },
        adjust: () => api.ocre_edit(find("#adjustment").value, Number(find("#adjustment-value").value)),
        undo: () => api.ocre_edit("undo", 0),
        redo: () => api.ocre_edit("redo", 0),
        reset: () => api.ocre_edit("reset", 0),
        export: () => api.ocre_export(),
        "open-project": () => api.ocre_project("open"),
        "save-project": () => api.ocre_project("save")
    };

    root.addEventListener("click", (event) => {
        const action = event.target.closest("[data-action]")?.dataset.action;
        if (action) void command(actions[action]);
        const view = event.target.closest("[data-view]")?.dataset.view;
        if (view === "fit") viewport.fit();
        if (view === "actual") viewport.changeZoom(1 / viewport.zoom);
        if (view === "out") viewport.changeZoom(1 / 1.2);
        if (view === "in") viewport.changeZoom(1.2);
        if (view === "clear-roi") {
            viewport.roi = null;
            viewport.draw();
        }
        if (view === "roi" || view === "pan") {
            viewport.mode = view;
            for (const mode of ["roi", "pan"]) {
                find(`[data-view="${mode}"]`).setAttribute("aria-pressed", String(mode === view));
            }
        }
    }, { signal });

    find("#preset").addEventListener("change", controls, { signal });
    find("#comparison").addEventListener("input", (event) => {
        viewport.divider = Number(event.target.value) / 100;
        viewport.draw();
    }, { signal });
    find("#maps").addEventListener("change", (event) => {
        void command(() => api.ocre_edit("map", event.target.value));
    }, { signal });

    window.addEventListener("vela:event", async (event) => {
        if (event.detail.name === "ocre:progress") status.textContent = event.detail.payload.message;
        if (event.detail.name !== "ocre:result") return;
        ++revision;
        const { error, result } = event.detail.payload;
        try {
            if (result) await present(result);
            status.textContent = error || result?.message || "Pronto";
        } catch {
            status.textContent = "Falha ao exibir a fotografia.";
        } finally {
            busy = false;
            controls();
        }
    }, { signal });

    controls();
    try {
        const state = await api.ocre_state();
        if (signal.aborted) return;
        busy = Boolean(state.busy);
        await present(state);
    } catch {
        status.textContent = "Falha ao recuperar o estado do editor.";
    }
    controls();
}

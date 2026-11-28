import { classicFilters, element, techniqueName, techniques } from "./techniques.js";

const labels = {
    queued: "Na fila", running: "Processando", done: "Concluída",
    failed: "Falha", cancelled: "Cancelada", skipped: "Sem área individual"
};

export class BatchView {
    constructor(root, catalog, api, signal, report, openResult, saveView) {
        this.root = root;
        this.catalog = catalog;
        this.api = api;
        this.report = report;
        this.openResult = openResult;
        this.saveView = saveView;
        this.form = root.querySelector("#batch-form");
        const methods = root.querySelector("#batch-methods");
        for (const [key, [name, help]] of Object.entries(techniques)) {
            const label = element("label", "", { class: "choice", title: help });
            const input = element("input", "", { type: "checkbox", class: "choice-input", name: "method", value: key });
            input.checked = key === "combinado";
            label.append(input, element("span", name));
            methods.append(label);
        }
        const classic = root.querySelector("#batch-classic-methods");
        let section;
        let group;
        for (const [key, [name, category]] of Object.entries(classicFilters)) {
            if (group !== category) {
                group = category;
                section = element("fieldset");
                section.append(element("legend", category));
                classic.append(section);
            }
            const label = element("label", "", { class: "choice" });
            label.append(element("input", "", {
                type: "checkbox", class: "choice-input", name: "method", value: key
            }), element("span", name));
            section.append(label);
        }
        const updateCount = () => {
            const count = classic.querySelectorAll("input:checked").length;
            root.querySelector("#batch-classic-count").textContent = count ? `${count} selecionados` : "";
        };
        classic.addEventListener("change", updateCount, { signal });
        this.form.querySelector("#batch-preset").addEventListener("change", (event) => {
            const preset = this.catalog.catalog?.presets[event.target.value];
            if (!preset) return;
            this.form.querySelectorAll('[name="method"]').forEach((input) => {
                input.checked = input.value === preset.technique;
            });
            updateCount();
            this.form.elements.strength.value = Math.round(preset.strength * 100);
        }, { signal });
        this.form.addEventListener("submit", (event) => {
            event.preventDefault();
            void this.start();
        }, { signal });
        const ticker = setInterval(() => this.updateElapsed(), 1000);
        signal.addEventListener("abort", () => clearInterval(ticker), { once: true });
        root.querySelector('[data-screen="batch"]').addEventListener("click", (event) => {
            const button = event.target.closest("[data-batch]");
            if (!button) return;
            const { batch, index } = button.dataset;
            if (batch === "open") this.openResult(this.state.tasks[Number(index)]);
            else void this.api.ocre_batch_control(batch, index === undefined ? null : Number(index))
                .then((state) => this.render(state)).catch((error) => report(error.message));
        }, { signal });
    }

    async start() {
        if (this.starting || this.state?.running) return;
        this.starting = true;
        const data = new FormData(this.form);
        const scope = data.get("scope");
        const active = this.catalog.photo;
        const folder = active?.split("/").slice(0, -1).join("/");
        const keys = scope === "all" ? this.catalog.catalog?.photos :
            scope === "current" ? [active].filter(Boolean) :
            scope === "folder" && active ? this.catalog.catalog?.photos.filter((name) =>
                name.split("/").slice(0, -1).join("/") === folder) :
                scope === "folder" ? [] : [...this.catalog.selected];
        this.form.querySelector("#start-batch").disabled = true;
        try {
            await this.saveView();
            await this.api.ocre_batch(keys ?? [], data.getAll("method"), {
                region: data.get("region"), format: data.get("format"),
                max_side: Number(data.get("max_side")), quality: Number(data.get("quality")),
                strength: Number(data.get("strength")) / 100,
                adjustments: this.catalog.catalog?.presets[data.get("preset")]?.adjustments ?? []
            });
            this.render(await this.api.ocre_batch_state());
        } catch (error) {
            this.report(error.message);
            this.form.querySelector("#start-batch").disabled = false;
        } finally {
            this.starting = false;
        }
    }

    updateElapsed() {
        if (!this.current?.started_at) return;
        const seconds = Math.max(0, Math.floor(Date.now() / 1000 - this.current.started_at));
        const elapsed = seconds < 60 ? `${seconds} s` :
            `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
        this.root.querySelector("#queue-elapsed").textContent = elapsed;
        const cell = this.root.querySelector("#queue [data-elapsed]");
        if (cell) cell.textContent = elapsed;
    }

    render(state) {
        this.state = state;
        const count = state.tasks.filter((task) => !["queued", "running"].includes(task.state)).length;
        const current = this.current = state.tasks.find((task) => task.state === "running");
        const queue = this.root.querySelector("#queue");
        const failed = state.tasks.filter((task) => task.state === "failed").length;
        const activity = current ? `${techniqueName(current.technique)} · ${current.photo}` :
            state.paused ? "Pausado" : state.running ? "Em andamento" : "Fila encerrada";
        const parts = [`${count} de ${state.tasks.length} tarefas`, activity];
        if (current && state.paused) parts.push("Pausa após esta tarefa");
        if (failed) parts.push(`${failed} com falha`);
        this.root.querySelector("#queue-status").textContent = state.tasks.length ?
            parts.join(" · ") : "Fila de processamento";
        this.root.querySelector("#queue-elapsed").textContent = "";
        this.root.querySelector("#queue-progress").max = Math.max(state.tasks.length, 1);
        this.root.querySelector("#queue-progress").value = count;
        this.form.querySelector("#start-batch").disabled = state.running;
        this.root.querySelector('[data-batch="pause"]').disabled = !state.running || state.paused;
        this.root.querySelector('[data-batch="resume"]').disabled = !state.paused;
        this.root.querySelector('[data-batch="cancel"]').disabled = !state.running;
        this.root.querySelector('[data-batch="retry"]').disabled = state.running ||
            !state.tasks.some((task) => task.state === "failed");
        this.catalog.statuses = new Map(state.tasks.map((task) => [task.photo, labels[task.state]]));
        this.catalog.update();
        const relevant = state.tasks.map((task, index) => [task, index]).slice(Math.max(0, count - 30), Math.max(120, count + 90));
        queue.replaceChildren(...relevant.map(([task, index]) => {
            const row = element("tr");
            for (const text of [
                task.photo, techniqueName(task.technique),
                [labels[task.state], task.device?.toUpperCase(), task.error].filter(Boolean).join(" · "),
                task.seconds ? `${task.seconds.toFixed(2)} s` : "—"
            ]) row.append(element("td", text));
            if (task === current) row.lastElementChild.setAttribute("data-elapsed", "");
            const actions = element("td");
            if (["queued", "done"].includes(task.state)) {
                actions.append(element("button", task.state === "queued" ? "Cancelar" : "Abrir", {
                    "data-batch": task.state === "queued" ? "cancel-task" : "open",
                    "data-index": index
                }));
            }
            row.append(actions);
            return row;
        }));
        this.updateElapsed();
    }
}

import { element, techniqueName, techniques } from "./techniques.js";

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
            const label = element("label", "", { title: help });
            const input = element("input", "", { type: "checkbox", name: "method", value: key });
            input.checked = key === "combinado";
            label.append(input, document.createTextNode(name));
            methods.append(label);
        }
        this.form.querySelector("#batch-preset").addEventListener("change", (event) => {
            const preset = this.catalog.catalog?.presets[event.target.value];
            if (!preset) return;
            this.form.querySelectorAll('[name="method"]').forEach((input) => {
                input.checked = input.value === preset.technique;
            });
            this.form.elements.strength.value = Math.round(preset.strength * 100);
        }, { signal });
        this.form.addEventListener("submit", (event) => {
            event.preventDefault();
            void this.start();
        }, { signal });
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
        }
    }

    render(state) {
        this.state = state;
        const count = state.tasks.filter((task) => !["queued", "running"].includes(task.state)).length;
        const current = state.tasks.find((task) => task.state === "running");
        const queue = this.root.querySelector("#queue");
        const title = state.tasks.length ?
            `${count} de ${state.tasks.length} tarefas · ${state.paused ? "Pausado" : current?.photo ?? (state.running ? "Em andamento" : "Fila encerrada")}` :
            "Fila de processamento";
        this.root.querySelector("#queue-status").textContent = title;
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
    }
}

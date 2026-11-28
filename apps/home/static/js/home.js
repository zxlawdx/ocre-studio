export async function mount(root, signal) {
    const api = window.pywebview.api;
    const status = root.querySelector("#home-status");
    const list = root.querySelector("#home-projects");
    const open = root.querySelector("[data-project-open]");
    if (!list || !open) return;
    let pending = false;

    function setPending(value) {
        pending = value;
        for (const button of [open, ...list.querySelectorAll("button[data-recent]")]) {
            button.disabled = value || button.dataset.missing === "true";
        }
    }

    async function openProject(action) {
        if (pending) return;
        setPending(true);
        status.textContent = "Abrindo projeto…";
        try {
            const dirty = await api.ocre_project_dirty();
            if (dirty && !window.confirm("O projeto atual tem alterações não salvas. Continuar?")) {
                status.textContent = "";
            } else {
                if (await action()) return;
                status.textContent = "";
            }
        } catch (error) {
            status.textContent = error.message;
        }
        setPending(false);
    }

    open.addEventListener("click", () => void openProject(() => api.ocre_project("open")), { signal });
    list.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-recent]");
        if (button) void openProject(() => api.ocre_open_recent(button.dataset.recent));
    }, { signal });
    window.addEventListener("vela:event", (event) => {
        if (!pending || event.detail.name !== "ocre:result") return;
        const { result, error } = event.detail.payload;
        setPending(false);
        if (error) status.textContent = error;
        else if (result?.catalog || result?.document) void window.Vela.navigate("/editor");
        else status.textContent = "";
    }, { signal });

    const empty = root.querySelector("#home-empty");
    try {
        const projects = await api.ocre_recent();
        if (signal.aborted) return;
        empty.hidden = projects.length > 0;
        empty.textContent = "Os projetos salvos ou abertos aparecem aqui.";
        for (const project of projects) {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.dataset.recent = project.path;
            button.dataset.missing = String(project.missing);
            button.title = project.path;
            const name = document.createElement("strong");
            const detail = document.createElement("span");
            name.textContent = project.name;
            detail.textContent = project.missing ? "Arquivo indisponível" :
                `${project.photos} fotografias · ${new Date(project.accessed).toLocaleDateString("pt-BR")}`;
            button.append(name, detail);
            item.append(button);
            list.append(item);
        }
        setPending(pending);
    } catch {
        empty.textContent = "Falha ao carregar projetos recentes.";
    }
}

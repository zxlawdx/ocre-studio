import { element } from "./techniques.js";

const basename = (path) => path.split("/").at(-1);
const PAGE = 160;

export class CatalogView {
    constructor(root, api, signal, open) {
        this.root = root;
        this.api = api;
        this.open = open;
        this.catalog = null;
        this.photo = null;
        this.selected = new Set();
        this.tabs = [];
        this.statuses = new Map();
        this.expanded = new Set();
        this.limit = PAGE;
        this.explorer = root.querySelector("#explorer");
        this.gallery = root.querySelector("#gallery");
        this.search = root.querySelector("#photo-search");
        this.search.addEventListener("input", () => { this.limit = PAGE; this.render(); }, { signal });
        for (const region of [this.explorer, this.gallery]) {
            region.addEventListener("click", (event) => {
                const key = event.target.closest("[data-photo]")?.dataset.photo;
                if (key !== undefined) {
                    this.select(key, event);
                    if (region === this.gallery && !event.ctrlKey && !event.shiftKey && !event.metaKey) {
                        this.open(key);
                    }
                }
                if (event.target.closest("[data-more]")) { this.limit += PAGE; this.render(); }
            }, { signal });
            region.addEventListener("keydown", (event) => {
                if (event.key.toLowerCase() === "a" && (event.ctrlKey || event.metaKey)) {
                    event.preventDefault();
                    this.selected = new Set(this.matching());
                    this.update();
                }
                const key = event.target.closest("[data-photo]")?.dataset.photo;
                if (event.key === "Enter" && key !== undefined) {
                    event.preventDefault();
                    this.open(key);
                }
            }, { signal });
        }
        this.explorer.addEventListener("dblclick", (event) => {
            const key = event.target.closest("[data-photo]")?.dataset.photo;
            if (key !== undefined) this.open(key);
        }, { signal });
        this.explorer.addEventListener("contextmenu", (event) => {
            const key = event.target.closest("[data-photo]")?.dataset.photo;
            if (key === undefined) return;
            event.preventDefault();
            this.context = key;
            root.querySelector("#catalog-context").hidden = false;
            root.querySelector("#catalog-context button").focus();
        }, { signal });
        this.observer = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                const image = entry.target;
                this.observer.unobserve(image);
                const identity = this.catalog?.root;
                void this.api.ocre_thumbnail(image.dataset.thumbnail).then((url) => {
                    if (url && image.isConnected && identity === this.catalog?.root) image.src = url;
                }).catch(() => {});
            }
        }, { root: this.gallery });
        signal.addEventListener("abort", () => this.observer.disconnect(), { once: true });
    }

    apply(catalog) {
        const same = catalog?.root === this.catalog?.root;
        this.catalog = catalog;
        if (!same) {
            this.selected.clear();
            this.expanded.clear();
            this.tabs = catalog?.tabs?.slice() ?? [];
            this.limit = PAGE;
            this.photo = null;
            this.statuses.clear();
        }
        this.root.querySelector("#project-heading").textContent = catalog?.name || "Sem projeto";
        this.root.querySelector("#project-summary").hidden = !catalog;
        if (catalog) {
            this.root.querySelector("#project-title").textContent = catalog.name;
            this.root.querySelector("#project-location").textContent = catalog.root;
            this.root.querySelector("#project-details").textContent =
                [`${catalog.photos.length} fotografias`, catalog.metadata.site, catalog.metadata.panel,
                    catalog.metadata.researcher].filter(Boolean).join(" · ");
        }
        this.render();
        this.renderTabs();
    }

    matching() {
        const value = this.search.value.trim().toLocaleLowerCase();
        return (this.catalog?.photos ?? []).filter((key) => key.toLocaleLowerCase().includes(value));
    }

    select(key, event) {
        if (event.shiftKey && this.anchor) {
            const list = this.matching();
            const start = list.indexOf(this.anchor);
            const end = list.indexOf(key);
            if (start >= 0 && end >= 0) {
                this.selected = new Set(list.slice(Math.min(start, end), Math.max(start, end) + 1));
            }
        } else if (event.ctrlKey || event.metaKey) {
            if (this.selected.has(key)) this.selected.delete(key);
            else this.selected.add(key);
            this.anchor = key;
        } else {
            this.selected = new Set([key]);
            this.anchor = key;
        }
        this.update();
    }

    render() {
        this.observer.disconnect();
        this.explorer.replaceChildren();
        this.gallery.replaceChildren();
        const photos = this.matching();
        const folders = new Map([["", this.explorer]]);
        for (const key of photos.slice(0, this.limit)) {
            let directory = "";
            for (const part of key.split("/").slice(0, -1)) {
                const parent = directory;
                directory = parent ? `${parent}/${part}` : part;
                if (!folders.has(directory)) {
                    const details = element("details");
                    const folderKey = directory;
                    details.open = this.expanded.has(folderKey) || this.search.value !== "";
                    details.addEventListener("toggle", () => {
                        if (details.open) this.expanded.add(folderKey);
                        else this.expanded.delete(folderKey);
                    });
                    details.append(element("summary", part));
                    folders.get(parent).append(details);
                    folders.set(folderKey, details);
                }
            }
            const row = element("button", "", {
                "data-photo": key, class: "photo-row", type: "button", title: key
            });
            row.append(element("span", "□", { "aria-hidden": "true", class: "photo-check" }),
                element("span", basename(key)));
            folders.get(directory).append(row);
            const frame = element("button", "", { "data-photo": key, type: "button", title: key });
            const image = element("img", "", { "data-thumbnail": key, alt: "" });
            frame.append(image, element("span", basename(key)));
            this.gallery.append(frame);
            this.observer.observe(image);
        }
        if (!photos.length) {
            this.explorer.append(element("p", this.catalog ? "Nenhuma fotografia encontrada." : "Abra uma pasta como projeto.", { class: "muted" }));
        }
        if (photos.length > this.limit) {
            this.explorer.append(element("button", "Mostrar mais fotografias", { "data-more": "", type: "button" }));
            this.gallery.append(element("button", "Mais fotografias", { "data-more": "", type: "button" }));
        }
        this.update();
    }

    update() {
        for (const item of this.root.querySelectorAll("[data-photo]")) {
            const key = item.dataset.photo;
            item.setAttribute("aria-pressed", String(this.selected.has(key)));
            if (key === this.photo) item.setAttribute("aria-current", "true");
            else item.removeAttribute("aria-current");
            const check = item.querySelector(".photo-check");
            if (check) check.textContent = this.selected.has(key) ? "✓" : "□";
            const status = this.statuses.get(key);
            const name = basename(key);
            item.setAttribute("aria-label", status ? `${name}, ${status}` : name);
            item.title = status ? `${key} · ${status}` : key;
        }
        this.root.querySelector("#selection-count").textContent = this.selected.size ?
            `${this.selected.size} de ${this.catalog?.photos.length ?? 0} selecionadas` : "Nenhuma fotografia selecionada";
    }

    activate(key) {
        this.photo = key;
        if (key && !this.tabs.includes(key)) this.tabs.push(key);
        this.renderTabs();
        this.update();
    }

    renderTabs() {
        const container = this.root.querySelector("#tabs");
        container.replaceChildren();
        for (const key of this.tabs) {
            const tab = element("div", "", { class: "document-tab" });
            if (key === this.photo) tab.setAttribute("aria-current", "true");
            tab.append(
                element("button", basename(key), { "data-tab": key, class: "tab-name", title: key }),
                element("button", "×", { "data-close-tab": key, "aria-label": `Fechar ${basename(key)}` })
            );
            container.append(tab);
        }
    }
}

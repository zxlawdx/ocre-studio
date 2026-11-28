import { adjustments, classicFilters, element, techniqueName } from "./techniques.js";

export function describeArea(region) {
    if (region === "auto") return "Região automática";
    if (region === "saved") return "Região de referência";
    if (!region?.length) return "Imagem inteira";
    const boxes = Array.isArray(region[0]) ? region : [region];
    return boxes.map(([x, y, right, bottom]) =>
        `${right - x} × ${bottom - y} px em (${x}, ${y})`).join(" · ");
}

export function filterName(name, value) {
    if (name === "equalize") return "Equalização de histograma";
    const classic = classicFilters[`classic_${name}_${value}`];
    return classic ? classic[0] : (adjustments[name]?.[0] ?? "Ajuste");
}

export function renderHistory(container, doc) {
    const row = (label, detail, index, current) => {
        const item = element("li");
        const action = index === null ? element("div") : element("button", "", {
            type: "button", "data-history": index, title: "Voltar a este estado"
        });
        if (current) action.setAttribute("aria-current", "step");
        action.append(element("strong", label), element("span", detail));
        item.append(action);
        return item;
    };
    const base = doc.map === "original" ? null : doc.provenance;
    const current = doc.history.length;
    const baked = base?.adjustments ?? [];
    const rows = [row("Fotografia original", doc.name, base ? null : 0, current === 0 && !base)];
    if (base?.preset) {
        const previous = base.input?.label;
        rows.push(row(techniqueName(base.preset),
            [describeArea(base.roi), previous && `Entrada: ${previous}`].filter(Boolean).join(" · "),
            baked.length ? null : 0, current === 0 && !baked.length));
    }
    for (const [index, step] of [...baked, ...doc.history].entries()) {
        const position = index + 1 - baked.length;
        const details = step.replace ? step.value.toLocaleString("pt-BR") : describeArea(step.regions);
        rows.push(row(filterName(step.name, step.value), details, position < 0 ? null : position,
            position === current));
    }
    container.replaceChildren(...rows.reverse());
}

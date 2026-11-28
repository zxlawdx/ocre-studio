export function mountDisclosures(root, signal) {
    const panels = root.querySelectorAll(
        ".history-panel, .inspector details, .workspace-page details, dialog details"
    );
    for (const panel of panels) {
        const summary = panel.querySelector(":scope > summary");
        if (!summary) continue;
        const content = document.createElement("div");
        const inner = document.createElement("div");
        content.className = "disclosure-content";
        inner.className = "disclosure-inner";
        while (summary.nextSibling) inner.append(summary.nextSibling);
        content.append(inner);
        panel.append(content);
        panel.addEventListener("toggle", () => {
            content.classList.toggle("disclosure-enter", panel.open);
        }, { signal });
    }
}

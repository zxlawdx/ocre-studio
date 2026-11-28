export function mountTabs(root, tablist, signal, onChange) {
    const tabs = [...tablist.querySelectorAll('[role="tab"]')];
    const panels = tabs.map((tab) => root.querySelector(`#${tab.getAttribute("aria-controls")}`));

    function select(selected) {
        if (selected.getAttribute("aria-selected") === "true") return;
        tabs.forEach((tab, index) => {
            const active = tab === selected;
            tab.setAttribute("aria-selected", String(active));
            tab.tabIndex = active ? 0 : -1;
            panels[index].hidden = !active;
        });
        onChange?.();
    }

    tablist.addEventListener("click", (event) => {
        const tab = event.target.closest('[role="tab"]');
        if (tabs.includes(tab)) select(tab);
    }, { signal });

    tablist.addEventListener("keydown", (event) => {
        const index = tabs.indexOf(event.target);
        if (index < 0 || event.altKey || event.ctrlKey || event.metaKey) return;
        const destination = new Map([
            ["ArrowLeft", (index + tabs.length - 1) % tabs.length],
            ["ArrowRight", (index + 1) % tabs.length],
            ["Home", 0],
            ["End", tabs.length - 1]
        ]).get(event.key);
        if (destination === undefined) return;
        event.preventDefault();
        select(tabs[destination]);
        tabs[destination].focus({ preventScroll: true });
    }, { signal });
}

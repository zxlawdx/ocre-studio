/** Keep the top-level disclosures exclusive and dismiss them like desktop menus. */
export function mountMenubar(bar, signal) {
    const menus = [...bar.querySelectorAll(":scope > details")];
    let active = null;

    function close(restoreFocus = false) {
        if (!active) return;
        const menu = active;
        active = null;
        menu.open = false;
        if (restoreFocus) menu.querySelector("summary").focus();
    }

    function position() {
        if (!active) return;
        const popup = active.querySelector(".popup");
        popup.style.removeProperty("--menu-offset");
        const { right } = popup.getBoundingClientRect();
        const overflow = right - (document.documentElement.clientWidth - 8);
        if (overflow > 0) popup.style.setProperty("--menu-offset", `${-overflow}px`);
    }

    for (const menu of menus) {
        menu.querySelector("summary").addEventListener("click", (event) => {
            event.preventDefault();
            const wasOpen = active === menu;
            close();
            if (!wasOpen) {
                active = menu;
                menu.open = true;
                position();
            }
        }, { signal });
    }
    bar.addEventListener("click", (event) => {
        if (event.target.closest(".popup button")) close();
    }, { signal });
    document.addEventListener("pointerdown", (event) => {
        if (!bar.contains(event.target)) close();
    }, { signal });
    document.addEventListener("focusin", (event) => {
        if (!bar.contains(event.target)) close();
    }, { signal });
    window.addEventListener("keydown", (event) => {
        if (active && event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            close(true);
        }
    }, { signal, capture: true });
    window.addEventListener("resize", position, { signal });
}

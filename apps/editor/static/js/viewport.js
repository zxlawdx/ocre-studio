import { canvasRegion, changeRegion, drawRegion, regionTarget, toImage } from "./region.js";

/** Synchronized photographic previews and a native-pixel region selection. */
export class Viewport {
    constructor(canvas, update, signal) {
        this.canvas = canvas;
        this.context = canvas.getContext("2d");
        this.overlay = canvas.parentElement.querySelector("#region-overlay");
        this.overlayContext = this.overlay.getContext("2d");
        this.comparison = "wipe";
        this.update = update;
        this.zoom = 1;
        this.pan = [0, 0];
        this.mode = "pan";
        this.divider = 0.5;
        this.roi = null;
        this.images = [];
        const observer = new ResizeObserver(() => this.draw());
        observer.observe(canvas);
        signal.addEventListener("abort", () => observer.disconnect(), { once: true });
        canvas.addEventListener("pointerdown", (event) => this.begin(event), { signal });
        canvas.addEventListener("pointermove", (event) => this.move(event), { signal });
        canvas.addEventListener("pointerup", () => this.finish(), { signal });
        canvas.addEventListener("pointercancel", () => this.cancel(), { signal });
        canvas.addEventListener("lostpointercapture", () => this.finish(), { signal });
        canvas.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                this.cancel();
            }
        }, { signal });
        canvas.addEventListener("wheel", (event) => {
            event.preventDefault();
            this.changeZoom(event.deltaY < 0 ? 1.15 : 1 / 1.15);
        }, { signal, passive: false });
    }

    async load(document, signal) {
        const sources = [document.original ?? this.original, document.processed];
        const replacing = Boolean(document.original);
        this.original = sources[0];
        const images = await Promise.all(sources.map(async (source) => {
            const image = new Image();
            image.src = source;
            await image.decode();
            return image;
        }));
        if (signal.aborted) return;
        this.dimensions = [document.original_width ?? document.width, document.original_height ?? document.height];
        this.images = images;
        if (replacing) {
            this.roi = Array.isArray(document.roi) ? document.roi : null;
            if (typeof document.view?.zoom === "number" && Array.isArray(document.view.pan)) {
                this.zoom = document.view.zoom;
                this.pan = document.view.pan;
                this.draw();
            } else {
                this.fit();
            }
        } else {
            this.draw();
        }
    }

    fit() {
        if (!this.images.length) return;
        const [image] = this.images;
        this.zoom = Math.min(
            this.canvas.clientWidth / image.width / (this.comparison === "side" ? 2 : 1),
            this.canvas.clientHeight / image.height
        ) * 0.96;
        this.pan = [0, 0];
        this.draw();
    }

    changeZoom(factor) {
        this.zoom = Math.min(12, Math.max(0.02, this.zoom * factor));
        this.draw();
    }

    bounds() {
        const [image] = this.images;
        const width = image.width * this.zoom;
        const height = image.height * this.zoom;
        return [
            (this.canvas.clientWidth - width) / 2 + this.pan[0],
            (this.canvas.clientHeight - height) / 2 + this.pan[1],
            width,
            height
        ];
    }

    draw() {
        const ratio = window.devicePixelRatio || 1;
        for (const layer of [this.canvas, this.overlay]) {
            const width = Math.round(this.canvas.clientWidth * ratio);
            const height = Math.round(this.canvas.clientHeight * ratio);
            if (layer.width !== width) layer.width = width;
            if (layer.height !== height) layer.height = height;
        }
        for (const context of [this.context, this.overlayContext]) {
            context.setTransform(ratio, 0, 0, ratio, 0, 0);
            context.clearRect(0, 0, this.canvas.clientWidth, this.canvas.clientHeight);
        }
        if (!this.images.length) return;
        const ctx = this.context;
        const bounds = this.bounds();
        const [x, y, width, height] = bounds;
        const split = x + width * this.divider;
        if (this.comparison === "side") {
            const half = this.canvas.clientWidth / 2;
            this.images.forEach((image, index) => {
                ctx.save();
                ctx.beginPath();
                ctx.rect(index * half, 0, half, this.canvas.clientHeight);
                ctx.clip();
                ctx.drawImage(image, x + (index - 0.5) * half, y, width, height);
                ctx.restore();
            });
        } else ctx.drawImage(this.images[this.comparison === "result" ? 1 : 0], ...bounds);
        if (this.comparison === "overlay") {
            ctx.save();
            ctx.globalAlpha = 1 - this.divider;
            ctx.drawImage(this.images[1], ...bounds);
            ctx.restore();
        }
        if (this.comparison === "wipe") {
            ctx.save();
            ctx.beginPath();
            ctx.rect(split, y, width * (1 - this.divider), height);
            ctx.clip();
            ctx.drawImage(this.images[1], ...bounds);
            ctx.restore();
            if (this.divider > 0 && this.divider < 1) {
                ctx.fillStyle = "#18191b";
                ctx.fillRect(split - 2, y, 4, height);
                ctx.fillStyle = "#faf8f3";
                ctx.fillRect(split - 1, y, 2, height);
                ctx.fillRect(split - 10, y + height / 2 - 8, 20, 16);
                ctx.fillStyle = "#232426";
                ctx.textAlign = "center";
                ctx.fillText("↔", split, y + height / 2 + 4);
            }
        }
        if (this.roi && this.comparison !== "side") drawRegion(this.overlayContext, this.roi, bounds, this.dimensions);
        this.update(Math.round(this.zoom * this.images[0].width / this.dimensions[0] * 100));
    }

    point(event) {
        const rect = this.canvas.getBoundingClientRect();
        return [event.clientX - rect.left, event.clientY - rect.top];
    }

    target(point) {
        if (!this.images.length) return null;
        const [x, y, width, height] = this.bounds();
        if (this.mode === "roi") {
            return this.roi ? regionTarget(point, canvasRegion(this.roi, this.bounds(), this.dimensions)) : null;
        }
        if (this.comparison === "wipe" && Math.abs(point[0] - x - width * this.divider) <= 9 &&
            point[1] >= y && point[1] <= y + height) return "divider";
        return null;
    }

    begin(event) {
        if (!this.images.length || event.button !== 0 || this.drag) return;
        const pointer = this.point(event);
        const handle = this.target(pointer);
        const [x, y, width, height] = this.bounds();
        if (this.mode === "roi" && !handle &&
            (pointer[0] < x || pointer[0] > x + width || pointer[1] < y || pointer[1] > y + height)) return;
        this.canvas.setPointerCapture(event.pointerId);
        this.drag = {
            id: event.pointerId, pointer, handle,
            point: toImage(pointer, this.bounds(), this.dimensions),
            region: handle ? this.roi : null, previous: this.roi, mode: this.mode
        };
    }

    move(event) {
        const pointer = this.point(event);
        if (!this.drag) {
            const target = this.target(pointer);
            this.canvas.style.cursor = target === "divider" ? "col-resize" :
                target === "move" ? "move" : target ? `${target}-resize` :
                    this.mode === "roi" ? "crosshair" : "grab";
            return;
        }
        if (event.pointerId !== this.drag.id) return;
        if (this.drag.handle === "divider") {
            const [x, , width] = this.bounds();
            this.divider = Math.max(0.02, Math.min(0.98, (pointer[0] - x) / width));
        } else if (this.drag.mode === "pan") {
            this.pan = this.pan.map((value, axis) => value + pointer[axis] - this.drag.pointer[axis]);
            this.drag.pointer = pointer;
        } else {
            const region = changeRegion(this.drag, toImage(pointer, this.bounds(), this.dimensions), this.dimensions);
            if (region) this.roi = region;
        }
        this.draw();
    }

    finish() {
        if (!this.drag) return;
        const changed = this.drag.mode === "roi" && this.roi !== this.drag.previous;
        this.drag = null;
        if (changed) this.onRegion?.(this.roi);
    }

    cancel() {
        const previous = this.drag ? this.drag.previous : null;
        this.drag = null;
        this.roi = previous;
        this.draw();
        this.onRegion?.(this.roi);
    }
}

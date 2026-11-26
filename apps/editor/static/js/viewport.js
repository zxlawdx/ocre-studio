/** Synchronized photographic previews and a native-pixel region selection. */
export class Viewport {
    constructor(canvas, update, signal) {
        this.canvas = canvas;
        this.context = canvas.getContext("2d");
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
        for (const name of ["pointerup", "pointercancel"]) {
            canvas.addEventListener(name, () => { this.drag = null; }, { signal });
        }
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
        this.dimensions = [document.width, document.height];
        this.images = images;
        if (replacing) {
            this.roi = document.provenance?.roi ?? null;
            this.fit();
        } else {
            this.draw();
        }
    }

    fit() {
        if (!this.images.length) return;
        const [image] = this.images;
        this.zoom = Math.min(
            this.canvas.clientWidth / image.width,
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
        this.canvas.width = Math.round(this.canvas.clientWidth * ratio);
        this.canvas.height = Math.round(this.canvas.clientHeight * ratio);
        if (!this.images.length) return;
        const ctx = this.context;
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        const [x, y, width, height] = this.bounds();
        const split = x + width * this.divider;
        ctx.drawImage(this.images[0], x, y, width, height);
        ctx.save();
        ctx.beginPath();
        ctx.rect(split, y, width * (1 - this.divider), height);
        ctx.clip();
        ctx.drawImage(this.images[1], x, y, width, height);
        ctx.restore();
        if (this.divider > 0 && this.divider < 1) {
            ctx.fillStyle = "#f1ece4";
            ctx.fillRect(split, y, 1, height);
        }
        if (this.roi) {
            const [left, top, right, bottom] = this.roi;
            const horizontal = width / this.dimensions[0];
            const vertical = height / this.dimensions[1];
            ctx.strokeStyle = "#e5a46c";
            ctx.setLineDash([5, 4]);
            ctx.strokeRect(
                x + left * horizontal, y + top * vertical,
                (right - left) * horizontal, (bottom - top) * vertical
            );
        }
        this.update(Math.round(this.zoom * 100));
    }

    imagePoint(event) {
        const [left, top, width, height] = this.bounds();
        const normalized = [(event.offsetX - left) / width, (event.offsetY - top) / height];
        return normalized.map((value, axis) =>
            Math.round(Math.max(0, Math.min(1, value)) * this.dimensions[axis])
        );
    }

    begin(event) {
        if (!this.images.length || event.button !== 0) return;
        this.canvas.setPointerCapture(event.pointerId);
        this.drag = { pointer: [event.clientX, event.clientY], point: this.imagePoint(event) };
    }

    move(event) {
        if (!this.drag) return;
        if (this.mode === "pan") {
            const pointer = [event.clientX, event.clientY];
            this.pan = this.pan.map((value, axis) => value + pointer[axis] - this.drag.pointer[axis]);
            this.drag.pointer = pointer;
        } else {
            const [startX, startY] = this.drag.point;
            const [endX, endY] = this.imagePoint(event);
            if (startX === endX || startY === endY) return;
            this.roi = [
                Math.min(startX, endX), Math.min(startY, endY),
                Math.max(startX, endX), Math.max(startY, endY)
            ];
        }
        this.draw();
    }
}

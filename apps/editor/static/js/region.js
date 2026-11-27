const clamp = (value, limit) => Math.max(0, Math.min(limit, value));

export function toImage(point, bounds, dimensions) {
    return point.map((value, axis) =>
        Math.round(clamp((value - bounds[axis]) / bounds[axis + 2] * dimensions[axis], dimensions[axis]))
    );
}

export function toCanvas(point, bounds, dimensions) {
    return point.map((value, axis) => bounds[axis] + value / dimensions[axis] * bounds[axis + 2]);
}

export function changeRegion(drag, point, dimensions) {
    const [x, y] = point;
    const [startX, startY] = drag.point;
    if (!drag.region) {
        if (x === startX || y === startY) return null;
        return [Math.min(x, startX), Math.min(y, startY), Math.max(x, startX), Math.max(y, startY)];
    }
    const [left, top, right, bottom] = drag.region;
    if (drag.handle === "move") {
        const dx = Math.max(-left, Math.min(dimensions[0] - right, x - startX));
        const dy = Math.max(-top, Math.min(dimensions[1] - bottom, y - startY));
        return [left + dx, top + dy, right + dx, bottom + dy];
    }
    return [
        drag.handle.includes("w") ? Math.min(x, right - 1) : left,
        drag.handle.includes("n") ? Math.min(y, bottom - 1) : top,
        drag.handle.includes("e") ? Math.max(x, left + 1) : right,
        drag.handle.includes("s") ? Math.max(y, top + 1) : bottom
    ];
}

function points(rectangle) {
    const [left, top, right, bottom] = rectangle;
    const x = (left + right) / 2;
    const y = (top + bottom) / 2;
    return [
        [left, top, "nw"], [x, top, "n"], [right, top, "ne"], [right, y, "e"],
        [right, bottom, "se"], [x, bottom, "s"], [left, bottom, "sw"], [left, y, "w"]
    ];
}

export function canvasRegion(region, bounds, dimensions) {
    return [
        ...toCanvas(region.slice(0, 2), bounds, dimensions),
        ...toCanvas(region.slice(2), bounds, dimensions)
    ];
}

export function regionTarget(point, rectangle) {
    const [x, y] = point;
    const [left, top, right, bottom] = rectangle;
    for (const [handleX, handleY, name] of points(rectangle)) {
        if (Math.hypot(x - handleX, y - handleY) <= 9) return name;
    }
    if (y >= top && y <= bottom) {
        if (Math.abs(x - left) <= 5) return "w";
        if (Math.abs(x - right) <= 5) return "e";
    }
    if (x >= left && x <= right) {
        if (Math.abs(y - top) <= 5) return "n";
        if (Math.abs(y - bottom) <= 5) return "s";
    }
    return x > left && x < right && y > top && y < bottom ? "move" : null;
}

export function drawRegion(context, region, bounds, dimensions) {
    const rectangle = canvasRegion(region, bounds, dimensions);
    const [left, top, right, bottom] = rectangle;
    const width = right - left;
    const height = bottom - top;
    context.save();
    context.fillStyle = "rgba(8, 9, 10, .44)";
    context.beginPath();
    context.rect(...bounds);
    context.rect(left, top, width, height);
    context.fill("evenodd");
    context.strokeStyle = "#121316";
    context.lineWidth = 5;
    context.strokeRect(left, top, width, height);
    context.strokeStyle = "#ffffff";
    context.lineWidth = 2;
    context.setLineDash([7, 4]);
    context.strokeRect(left, top, width, height);
    context.setLineDash([]);
    context.lineWidth = 2;
    for (const [x, y] of points(rectangle)) {
        context.fillStyle = "#fff";
        context.strokeStyle = "#16181b";
        context.fillRect(x - 5, y - 5, 10, 10);
        context.strokeRect(x - 5, y - 5, 10, 10);
    }
    const label = `${region[2] - region[0]} × ${region[3] - region[1]} px`;
    context.font = "12px system-ui";
    const labelY = top >= 27 ? top - 25 : top + 8;
    context.fillStyle = "#18191c";
    context.fillRect(left + 6, labelY, context.measureText(label).width + 14, 20);
    context.fillStyle = "#fff";
    context.fillText(label, left + 13, labelY + 14);
    context.restore();
}

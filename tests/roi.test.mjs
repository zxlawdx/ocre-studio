import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../apps/editor/static/js/region.js", import.meta.url));
const { canvasRegion, changeRegion, regionTarget, toCanvas, toImage } =
    await import(`data:text/javascript;base64,${source.toString("base64")}`);

test("image coordinates survive preview scaling and panning", () => {
    const bounds = [-120.25, 142.5, 615.5, 410.25];
    const dimensions = [6000, 4000];
    const point = [2381, 1729];
    assert.deepEqual(toImage(toCanvas(point, bounds, dimensions), bounds, dimensions), point);
    assert.deepEqual(toImage([-500, -400], bounds, dimensions), [0, 0]);
    assert.deepEqual(toImage([3000, 1800], bounds, dimensions), dimensions);
});

test("ROI accepts reverse drags and clamps a move without changing its size", () => {
    const region = changeRegion({ point: [50, 40] }, [10, 20], [100, 100]);
    assert.deepEqual(region, [10, 20, 50, 40]);
    assert.deepEqual(changeRegion({ point: [20, 30], region, handle: "move" }, [100, 100], [100, 100]),
        [60, 80, 100, 100]);
});

test("all eight handles remain reachable after zoom and resize stops at one native pixel", () => {
    const rectangle = canvasRegion([10, 15, 70, 75], [40, 70, 200, 200], [100, 100]);
    const [x, y, right, bottom] = rectangle;
    assert.deepEqual([
        [x, y], [(x + right) / 2, y], [right, y], [right, (y + bottom) / 2],
        [right, bottom], [(x + right) / 2, bottom], [x, bottom], [x, (y + bottom) / 2]
    ].map((point) => regionTarget(point, rectangle)), ["nw", "n", "ne", "e", "se", "s", "sw", "w"]);
    assert.deepEqual(changeRegion({ point: [10, 15], region: [10, 15, 70, 75], handle: "nw" }, [100, 100], [100, 100]), [69, 74, 70, 75]);
});

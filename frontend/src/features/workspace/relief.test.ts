import { describe, expect, it } from "vitest";

import { terrarium } from "../map/dem";
import { TILE_PX, tileFrame } from "./geometry";
import { buildRelief, contourLevels, demCover, heightOf, mercX, mercY, paintSlice, RELIEF_MAX_PX } from "./relief";

// quadra de ~1 km em Brusque
const ring = [
  [-48.93, -27.115],
  [-48.92, -27.115],
  [-48.92, -27.105],
  [-48.93, -27.105],
  [-48.93, -27.115],
];

describe("relief", () => {
  it("decodes terrarium pixels", () => {
    expect(terrarium(128, 0, 0)).toBe(0);
    expect(terrarium(128, 100, 128)).toBe(100.5);
  });

  it("frames the polygon like the other layers", () => {
    const f = tileFrame(ring);
    expect(f.x(-48.925)).toBeCloseTo(TILE_PX / 2);
    expect(f.lon(f.x(-48.93))).toBeCloseTo(-48.93);
    expect(f.lat(f.y(-27.11))).toBeCloseTo(-27.11);
  });

  it("picks round contour intervals", () => {
    expect(contourLevels(18, 142)).toEqual({ step: 10, levels: [20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140] });
    expect(contourLevels(20, 50).step).toBe(2.5);
    expect(contourLevels(10, 10.4).levels).toEqual([]);
  });

  it("covers the polygon with at most nine DEM tiles", () => {
    const c = demCover(tileFrame(ring).bbox);
    expect(c.z).toBe(13);
    expect(c.nx * c.ny).toBeLessThanOrEqual(9);
    expect(demCover([-49.1, -27.3, -48.7, -26.9]).nx).toBeLessThanOrEqual(3);
  });

  it("builds a sloped model capped below the next layer", () => {
    const frame = tileFrame(ring);
    const cover = demCover(frame.bbox);
    const [w, h] = [cover.nx * 256, cover.ny * 256];
    // rampa leste-oeste: 50 m no oeste do polígono, 150 m no leste
    const west = mercX(-48.93, cover.z) - cover.x0 * 256;
    const east = mercX(-48.92, cover.z) - cover.x0 * 256;
    const mosaic = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) mosaic[y * w + x] = 50 + (100 * (x + 0.5 - west)) / (east - west);
    }
    expect(mercY(-27.11, cover.z)).toBeGreaterThan(cover.y0 * 256);
    const size = 120;
    const relief = buildRelief(mosaic, cover, frame, new Float32Array(size * size).fill(1), size);
    expect(relief.min).toBeLessThan(55);
    expect(relief.max).toBeGreaterThan(145);
    expect(relief.step).toBe(10);
    expect(heightOf(relief, relief.max)).toBeLessThanOrEqual(RELIEF_MAX_PX + 1e-6);

    const out = new Uint8ClampedArray(size * size * 4);
    paintSlice(out, relief, 100, [0, 0, 255], { line: 1, fill: 0.1, halfWidth: 0.6 });
    const alpha = (i: number) => out[(60 * size + i) * 4 + 3] ?? 0;
    expect(alpha(5)).toBe(0); // oeste, abaixo da curva de 100 m
    expect(alpha(115)).toBeGreaterThan(0); // leste, acima
  });
});

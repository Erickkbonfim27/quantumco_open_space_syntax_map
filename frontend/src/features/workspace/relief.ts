import type { Position } from "geojson";

import { DEM_TILES, terrarium } from "../map/dem";
import { TILE_PX, type TileFrame, tileFrame } from "./geometry";

/**
 * Maquete de relevo do N1: o DEM do mapa (Terrain Tiles da AWS) recortado pelo polígono e
 * fatiado em curvas de nível; cada fatia sobe no ladrilho (translateZ) conforme a altitude.
 */

/** Altura máxima da maquete (px CSS): abaixo dos 80 px entre as camadas da pilha. */
export const RELIEF_MAX_PX = 56;
const MAX_EXAGGERATION = 3;
const MAX_LEVELS = 14;
// z13 é o mesmo zoom do sombreamento do mapa: o navegador costuma já ter os tiles em cache
const DEM_MAX_ZOOM = 13;
const DEM_MIN_ZOOM = 8;
const DEM_MAX_TILES = 9;
const TILE = 256;

export const mercX = (lon: number, z: number) => ((lon + 180) / 360) * TILE * 2 ** z;
export function mercY(lat: number, z: number): number {
  const s = Math.sin((lat * Math.PI) / 180);
  return (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * TILE * 2 ** z;
}

export interface TileCover {
  z: number;
  x0: number;
  y0: number;
  nx: number;
  ny: number;
}

/** Tiles do DEM que cobrem a caixa, no maior zoom com até 9 tiles. */
export function demCover([w, s, e, n]: [number, number, number, number]): TileCover {
  const at = (z: number): TileCover => {
    const x0 = Math.floor(mercX(w, z) / TILE);
    const y0 = Math.floor(mercY(n, z) / TILE);
    return {
      z,
      x0,
      y0,
      nx: Math.floor(mercX(e, z) / TILE) - x0 + 1,
      ny: Math.floor(mercY(s, z) / TILE) - y0 + 1,
    };
  };
  for (let z = DEM_MAX_ZOOM; z > DEM_MIN_ZOOM; z--) {
    const cover = at(z);
    if (cover.nx * cover.ny <= DEM_MAX_TILES) return cover;
  }
  return at(DEM_MIN_ZOOM);
}

/** Curvas "redondas" (1, 2, 2,5 ou 5 × 10ᵏ m), no máximo 14, estritamente acima do mínimo. */
export function contourLevels(min: number, max: number): { step: number; levels: number[] } {
  const range = max - min;
  if (!Number.isFinite(range) || range < 1) return { step: 0, levels: [] };
  let step = 1;
  search: for (let k = 0; k < 6; k++) {
    for (const m of [1, 2, 2.5, 5]) {
      step = m * 10 ** k;
      if (range / step <= MAX_LEVELS) break search;
    }
  }
  const levels: number[] = [];
  for (let i = Math.floor(min / step) + 1; i * step <= max; i++) levels.push(i * step);
  return { step, levels };
}

export interface Relief {
  /** lado do raster (px) — o ladrilho tem 240 px CSS */
  size: number;
  elev: Float32Array;
  /** declividade em metros por px do raster (para curvas de espessura constante) */
  grad: Float32Array;
  /** 0–1: dentro do polígono (borda suavizada) */
  mask: Float32Array;
  min: number;
  max: number;
  step: number;
  levels: number[];
  /** escala vertical da maquete (1 = verdadeira) */
  exaggeration: number;
  /** px CSS de altura por metro de desnível (já com a escala vertical) */
  zScale: number;
}

export const heightOf = (relief: Relief, level: number) => (level - relief.min) * relief.zScale;

/** Média móvel em linhas e colunas, no lugar: suaviza as quinas da interpolação bilinear. */
function boxBlur(data: Float32Array, size: number, radius: number): void {
  const line = new Float32Array(size);
  for (const horizontal of [true, false]) {
    for (let a = 0; a < size; a++) {
      const at = (b: number) => (horizontal ? a * size + b : b * size + a);
      for (let b = 0; b < size; b++) line[b] = data[at(b)] ?? 0;
      let sum = 0;
      for (let b = -radius; b <= radius; b++) sum += line[Math.min(size - 1, Math.max(0, b))] ?? 0;
      for (let b = 0; b < size; b++) {
        data[at(b)] = sum / (2 * radius + 1);
        sum += (line[Math.min(size - 1, b + radius + 1)] ?? 0) - (line[Math.max(0, b - radius)] ?? 0);
      }
    }
  }
}

/** Monta o raster de altitudes do ladrilho a partir do mosaico de tiles do DEM. */
export function buildRelief(
  mosaic: Float32Array,
  cover: TileCover,
  frame: TileFrame,
  mask: Float32Array,
  size: number,
): Relief {
  const [mw, mh] = [cover.nx * TILE, cover.ny * TILE];
  const k = TILE_PX / size;
  const mx = new Float32Array(size);
  const my = new Float32Array(size);
  for (let i = 0; i < size; i++) {
    mx[i] = mercX(frame.lon((i + 0.5) * k), cover.z) - cover.x0 * TILE - 0.5;
    my[i] = mercY(frame.lat((i + 0.5) * k), cover.z) - cover.y0 * TILE - 0.5;
  }
  const sample = (u: number, v: number) => {
    const x = Math.min(mw - 1.001, Math.max(0, u));
    const y = Math.min(mh - 1.001, Math.max(0, v));
    const [x0, y0] = [Math.floor(x), Math.floor(y)];
    const [fx, fy] = [x - x0, y - y0];
    const p = y0 * mw + x0;
    const top = (mosaic[p] ?? 0) * (1 - fx) + (mosaic[p + 1] ?? 0) * fx;
    const bottom = (mosaic[p + mw] ?? 0) * (1 - fx) + (mosaic[p + mw + 1] ?? 0) * fx;
    return top * (1 - fy) + bottom * fy;
  };
  const elev = new Float32Array(size * size);
  for (let j = 0; j < size; j++) {
    for (let i = 0; i < size; i++) elev[j * size + i] = sample(mx[i] ?? 0, my[j] ?? 0);
  }
  const rasterPerDem = 1 / Math.max(Math.abs((mx[1] ?? 1) - (mx[0] ?? 0)), 1e-6);
  const radius = Math.min(8, Math.max(1, Math.round(rasterPerDem / 2)));
  boxBlur(elev, size, radius);
  boxBlur(elev, size, radius);

  const grad = new Float32Array(size * size);
  let [min, max] = [Infinity, -Infinity];
  for (let j = 0; j < size; j++) {
    for (let i = 0; i < size; i++) {
      const p = j * size + i;
      const e = (di: number, dj: number) =>
        elev[Math.min(size - 1, Math.max(0, j + dj)) * size + Math.min(size - 1, Math.max(0, i + di))] ?? 0;
      grad[p] = Math.hypot((e(1, 0) - e(-1, 0)) / 2, (e(0, 1) - e(0, -1)) / 2);
      if ((mask[p] ?? 0) >= 0.5) {
        const v = elev[p] ?? 0;
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
  }
  if (min > max) [min, max] = [0, 0];
  const { step, levels } = contourLevels(min, max);
  const truePx = (max - min) * frame.pxPerMeter;
  const exaggeration = truePx > 0 ? Math.min(MAX_EXAGGERATION, RELIEF_MAX_PX / truePx) : 1;
  return { size, elev, grad, mask, min, max, step, levels, exaggeration, zScale: frame.pxPerMeter * exaggeration };
}

/**
 * Pinta uma fatia (tudo acima de `level`) em RGBA: véu leve por dentro e a curva de nível
 * na borda, com espessura constante na tela.
 */
export function paintSlice(
  out: Uint8ClampedArray,
  relief: Relief,
  level: number,
  rgb: readonly [number, number, number],
  { line, fill, halfWidth }: { line: number; fill: number; halfWidth: number },
): void {
  const { elev, grad, mask, size } = relief;
  out.fill(0);
  for (let p = 0; p < size * size; p++) {
    const m = mask[p] ?? 0;
    if (m <= 0) continue;
    const d = ((elev[p] ?? 0) - level) / Math.max(grad[p] ?? 0, 1e-3); // px até a curva (+ acima)
    if (d < -halfWidth - 1) continue;
    const l = Math.min(1, Math.max(0, halfWidth + 0.5 - Math.abs(d))) * line;
    const f = Math.min(1, Math.max(0, d + 0.5)) * fill;
    const a = (l + f * (1 - l)) * m;
    if (a <= 0) continue;
    const o = p * 4;
    out[o] = rgb[0];
    out[o + 1] = rgb[1];
    out[o + 2] = rgb[2];
    out[o + 3] = a * 255;
  }
}

async function fetchMosaic(cover: TileCover, signal?: AbortSignal): Promise<Float32Array> {
  const [w, h] = [cover.nx * TILE, cover.ny * TILE];
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const g = canvas.getContext("2d", { willReadFrequently: true });
  if (!g) throw new Error("canvas indisponível");
  const jobs: Promise<void>[] = [];
  for (let dy = 0; dy < cover.ny; dy++) {
    for (let dx = 0; dx < cover.nx; dx++) {
      const url = DEM_TILES.replace("{z}", String(cover.z))
        .replace("{x}", String(cover.x0 + dx))
        .replace("{y}", String(cover.y0 + dy));
      jobs.push(
        (async () => {
          const res = await fetch(url, { signal });
          if (!res.ok) throw new Error(`DEM ${res.status}`);
          // sem conversão de cor: os canais RGB são a altitude codificada
          const bitmap = await createImageBitmap(await res.blob(), {
            colorSpaceConversion: "none",
            premultiplyAlpha: "none",
          });
          g.drawImage(bitmap, dx * TILE, dy * TILE);
          bitmap.close();
        })(),
      );
    }
  }
  await Promise.all(jobs);
  const px = g.getImageData(0, 0, w, h).data;
  const out = new Float32Array(w * h);
  for (let i = 0; i < out.length; i++) out[i] = terrarium(px[i * 4] ?? 0, px[i * 4 + 1] ?? 0, px[i * 4 + 2] ?? 0);
  return out;
}

function polygonMask(ring: Position[], frame: TileFrame, size: number): Float32Array {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const g = canvas.getContext("2d", { willReadFrequently: true });
  const mask = new Float32Array(size * size);
  if (!g) return mask.fill(1);
  const k = size / TILE_PX;
  g.beginPath();
  ring.forEach(([x = 0, y = 0], i) => {
    if (i) g.lineTo(frame.x(x) * k, frame.y(y) * k);
    else g.moveTo(frame.x(x) * k, frame.y(y) * k);
  });
  g.closePath();
  g.fillStyle = "#fff";
  g.fill();
  const data = g.getImageData(0, 0, size, size).data;
  for (let p = 0; p < mask.length; p++) mask[p] = (data[p * 4 + 3] ?? 0) / 255;
  return mask;
}

/** Baixa o DEM do polígono e monta a maquete (raster em 2× para telas retina). */
export async function loadRelief(ring: Position[], signal?: AbortSignal): Promise<Relief> {
  const frame = tileFrame(ring);
  const [w, s, e, n] = frame.bbox;
  const [mx, my] = [(e - w) * 0.08, (n - s) * 0.08]; // margem para a suavização na borda
  const cover = demCover([w - mx, s - my, e + mx, n + my]);
  const mosaic = await fetchMosaic(cover, signal);
  const size = Math.round(TILE_PX * Math.min(2, Math.max(1, window.devicePixelRatio || 1)));
  return buildRelief(mosaic, cover, frame, polygonMask(ring, frame, size), size);
}

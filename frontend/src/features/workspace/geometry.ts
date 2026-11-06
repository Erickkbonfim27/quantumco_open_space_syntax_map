import type { Position } from "geojson";

/** Ponto dentro do anel (ray casting) em coordenadas lon/lat. */
export function inRing(ring: Position[], x: number, y: number): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi = 0, yi = 0] = ring[i] ?? [];
    const [xj = 0, yj = 0] = ring[j] ?? [];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Classe mediana (ponderada por km) de uma distribuição de 7 classes. */
export function medianClass(km: number[] | undefined): number | null {
  if (!km) return null;
  const total = km.reduce((a, b) => a + b, 0);
  if (total <= 0) return null;
  let acc = 0;
  for (let i = 0; i < km.length; i++) {
    acc += km[i] ?? 0;
    if (acc >= total / 2) return i;
  }
  return km.length - 1;
}

/** Lado do ladrilho de cada camada (px CSS); o polígono ocupa os 200 px centrais. */
export const TILE_PX = 240;
const FIT_PX = 200;
const METERS_PER_DEGREE = 111_320;

/** Enquadramento de um polígono no ladrilho: o mesmo em todas as camadas da pilha. */
export interface TileFrame {
  x: (lon: number) => number;
  y: (lat: number) => number;
  lon: (x: number) => number;
  lat: (y: number) => number;
  /** px por grau de latitude */
  scale: number;
  pxPerMeter: number;
  /** [oeste, sul, leste, norte] */
  bbox: [number, number, number, number];
}

export function tileFrame(ring: Position[]): TileFrame {
  const xs = ring.map((p) => p[0] ?? 0);
  const ys = ring.map((p) => p[1] ?? 0);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const kx = Math.cos((((y0 + y1) / 2) * Math.PI) / 180); // aspecto em lon/lat
  const scale = FIT_PX / Math.max((x1 - x0) * kx, y1 - y0, 1e-9);
  const [cx, cy, c] = [(x0 + x1) / 2, (y0 + y1) / 2, TILE_PX / 2];
  return {
    x: (lon) => c + (lon - cx) * kx * scale,
    y: (lat) => c - (lat - cy) * scale,
    lon: (px) => cx + (px - c) / (kx * scale),
    lat: (py) => cy - (py - c) / scale,
    scale,
    pxPerMeter: scale / METERS_PER_DEGREE,
    bbox: [x0, y0, x1, y1],
  };
}

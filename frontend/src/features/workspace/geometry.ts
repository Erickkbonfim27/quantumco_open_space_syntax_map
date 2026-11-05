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

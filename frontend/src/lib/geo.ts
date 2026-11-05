import type { Geometry, Position } from "geojson";

export type Bounds = [[number, number], [number, number]];

function* positions(geometry: Geometry): Generator<Position> {
  switch (geometry.type) {
    case "Point":
      yield geometry.coordinates;
      break;
    case "MultiPoint":
    case "LineString":
      yield* geometry.coordinates;
      break;
    case "MultiLineString":
    case "Polygon":
      for (const ring of geometry.coordinates) yield* ring;
      break;
    case "MultiPolygon":
      for (const polygon of geometry.coordinates) for (const ring of polygon) yield* ring;
      break;
    case "GeometryCollection":
      for (const child of geometry.geometries) yield* positions(child);
      break;
  }
}

export function boundsOf(geometries: Iterable<Geometry>): Bounds | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const geometry of geometries) {
    for (const [x, y] of positions(geometry)) {
      if (x === undefined || y === undefined) continue;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  return Number.isFinite(minX) ? [[minX, minY], [maxX, maxY]] : null;
}

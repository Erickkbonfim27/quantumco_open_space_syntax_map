import { describe, expect, it } from "vitest";

import { boundsOf } from "./geo";
import { formatKm, formatMeters, percent } from "./format";

describe("format", () => {
  it("formats distances in pt-BR", () => {
    expect(formatKm(2308096.7)).toBe("2.308,1 km");
    expect(formatMeters(183.4)).toBe("183 m");
    expect(formatMeters(1500)).toBe("1,5 km");
  });

  it("formats percentages and guards against zero", () => {
    expect(percent(25, 1000)).toBe("2,5%");
    expect(percent(1, 0)).toBe("–");
  });
});

describe("boundsOf", () => {
  it("returns the bounding box of mixed geometries", () => {
    expect(
      boundsOf([
        { type: "LineString", coordinates: [[-48.9, -27.1], [-48.8, -27.0]] },
        { type: "Polygon", coordinates: [[[-49.0, -27.2], [-48.95, -27.2], [-49.0, -27.15], [-49.0, -27.2]]] },
      ]),
    ).toEqual([[-49.0, -27.2], [-48.8, -27.0]]);
  });

  it("returns null when there is nothing to bound", () => {
    expect(boundsOf([])).toBeNull();
  });
});

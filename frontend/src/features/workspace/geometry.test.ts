import { describe, expect, it } from "vitest";

import { inRing, medianClass } from "./geometry";

describe("workspace geometry", () => {
  const square = [
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
    [0, 0],
  ];

  it("detects points inside a ring", () => {
    expect(inRing(square, 5, 5)).toBe(true);
    expect(inRing(square, 15, 5)).toBe(false);
  });

  it("finds the length-weighted median class", () => {
    expect(medianClass([0, 0, 1, 0, 0, 0, 5])).toBe(6);
    expect(medianClass([4, 0, 0, 0, 0, 0, 1])).toBe(0);
    expect(medianClass([0, 0, 0, 0, 0, 0, 0])).toBeNull();
  });
});

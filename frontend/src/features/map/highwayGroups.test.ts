import { describe, expect, it } from "vitest";

import { HIGHWAY_GROUPS, groupFor, lineColor } from "./highwayGroups";

// classes aceitas por methodology/v1/highway_filter.yaml (base + buffer)
const ACCEPTED = [
  "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
  "road", "living_street", "pedestrian", "steps", "service", "track",
  "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
];

describe("highway groups", () => {
  it("covers every class the methodology accepts", () => {
    for (const highway of ACCEPTED) expect(groupFor(highway), highway).toBeDefined();
  });

  it("assigns each class to exactly one group", () => {
    const all = HIGHWAY_GROUPS.flatMap((g) => g.classes);
    expect(new Set(all).size).toBe(all.length);
  });

  it("builds a match expression with a fallback", () => {
    const expression = lineColor() as unknown[];
    expect(expression[0]).toBe("match");
    expect(expression.length).toBe(3 + HIGHWAY_GROUPS.length * 2);
  });
});

import { describe, expect, it } from "vitest";

import { SYNTAX_PALETTE, syntaxClass } from "./syntaxPalette";

describe("syntax palette", () => {
  it("has 7 classes from blue to red", () => {
    expect(SYNTAX_PALETTE).toHaveLength(7);
    expect(SYNTAX_PALETTE[0]).toBe("#2233D6");
    expect(SYNTAX_PALETTE[6]).toBe("#E3231E");
  });

  it("maps percentiles to classes, clamping the ends", () => {
    expect(syntaxClass(0)).toBe(0);
    expect(syntaxClass(0.5)).toBe(3);
    expect(syntaxClass(0.999)).toBe(6);
    expect(syntaxClass(1)).toBe(6);
    expect(syntaxClass(-0.2)).toBe(0);
    expect(syntaxClass(1.7)).toBe(6);
  });
});

import { describe, expect, it } from "vitest";

import { CameraStore } from "./cameraStore";

describe("camera store", () => {
  it("keeps the bearing continuous across ±180°", () => {
    const store = new CameraStore();
    store.set(179, 0);
    store.set(-179, 0);
    expect(store.get().bearing).toBeCloseTo(181);
    store.set(-90, 30);
    expect(store.get()).toEqual({ bearing: 270, pitch: 30 });
  });

  it("notifies only when rotation or tilt change", () => {
    const store = new CameraStore();
    let calls = 0;
    const off = store.subscribe(() => calls++);
    store.set(0, 0);
    store.set(10, 0);
    store.set(10, 45);
    store.set(10, 45);
    off();
    store.set(20, 45);
    expect(calls).toBe(2);
  });
});

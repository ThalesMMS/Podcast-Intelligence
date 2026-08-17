import { describe, expect, it } from "vitest";

import { getNextTabIndex } from "../lib/tabs";

describe("tab keyboard navigation", () => {
  it.each([
    [0, "ArrowRight", 1],
    [1, "ArrowRight", 0],
    [0, "ArrowLeft", 1],
    [1, "ArrowLeft", 0],
    [1, "Home", 0],
    [0, "End", 1],
  ])("moves from tab %i with %s to %i", (current, key, expected) => {
    expect(getNextTabIndex(current, key, 2)).toBe(expected);
  });

  it("leaves unrelated keys to their native behavior", () => {
    expect(getNextTabIndex(0, "Tab", 2)).toBeNull();
    expect(getNextTabIndex(0, "Enter", 2)).toBeNull();
  });
});

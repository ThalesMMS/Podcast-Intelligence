import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

describe("dependency security adapters", () => {
  it("keeps brace-expansion callable for legacy minimatch consumers", () => {
    const expand = require("brace-expansion") as {
      (pattern: string): string[];
      expand: (pattern: string) => string[];
    };

    expect(expand("episode-{1,2}.json")).toEqual(["episode-1.json", "episode-2.json"]);
    expect(expand.expand("job-{a,b}.json")).toEqual(["job-a.json", "job-b.json"]);
  });
});

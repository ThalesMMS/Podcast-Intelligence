import { describe, expect, it } from "vitest";

import { getJobPanelMode } from "../lib/job-presentation";

describe("mobile job panel priority", () => {
  it.each(["queued", "running", "retrying", "waiting_for_user", "failed"] as const)(
    "keeps %s jobs prominent",
    (status) => {
      expect(getJobPanelMode(status)).toBe("priority");
    },
  );

  it("allows completed jobs to collapse after the artifact", () => {
    expect(getJobPanelMode("completed")).toBe("completed");
  });

  it("keeps cancelled jobs secondary", () => {
    expect(getJobPanelMode("cancelled")).toBe("secondary");
  });
});

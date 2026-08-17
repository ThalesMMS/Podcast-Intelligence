import { describe, expect, it } from "vitest";

import { episodeStatusFromJob, getWorkspaceRefreshPlan } from "../lib/workspace-polling";
import type { Job, Step } from "../lib/types";

function job(status: Job["status"], completedSteps: string[] = []): Job {
  const steps = ["resolve_source", "transcribe", "summarize", "finalize"].map(
    (name, ordinal) =>
      ({
        name,
        ordinal,
        status: completedSteps.includes(name) ? "completed" : "pending",
        attempts: 1,
        started_at: null,
        completed_at: null,
        error_message: null,
        metrics_json: {},
      }) satisfies Step,
  );
  return {
    id: "job-id",
    episode_id: "episode-id",
    status,
    current_step: null,
    progress: 0,
    error_code: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    steps,
  };
}

describe("episode workspace polling", () => {
  it("uses the lightweight job state without reloading unchanged artifacts", () => {
    const previous = job("running", ["resolve_source"]);
    const current = { ...job("running", ["resolve_source"]), progress: 0.4 };

    expect(getWorkspaceRefreshPlan(previous, current)).toEqual({
      continuePolling: true,
      refreshEpisode: false,
      refreshTranscript: false,
    });
  });

  it("reloads the transcript only when transcription becomes available", () => {
    const previous = job("running", ["resolve_source"]);
    const current = job("running", ["resolve_source", "transcribe"]);

    expect(getWorkspaceRefreshPlan(previous, current)).toEqual({
      continuePolling: true,
      refreshEpisode: false,
      refreshTranscript: true,
    });
    expect(getWorkspaceRefreshPlan(current, current).refreshTranscript).toBe(false);
  });

  it("reloads episode details when summary or terminal state changes", () => {
    const transcribed = job("running", ["resolve_source", "transcribe"]);
    const summarized = job("running", ["resolve_source", "transcribe", "summarize"]);
    const completed = job("completed", ["resolve_source", "transcribe", "summarize", "finalize"]);

    expect(getWorkspaceRefreshPlan(transcribed, summarized).refreshEpisode).toBe(true);
    expect(getWorkspaceRefreshPlan(summarized, completed)).toEqual({
      continuePolling: false,
      refreshEpisode: true,
      refreshTranscript: false,
    });
  });

  it("derives visible episode status from job state", () => {
    expect(episodeStatusFromJob("queued", "running")).toBe("processing");
    expect(episodeStatusFromJob("processing", "retrying")).toBe("processing");
    expect(episodeStatusFromJob("processing", "completed")).toBe("ready");
    expect(episodeStatusFromJob("processing", "failed")).toBe("failed");
    expect(episodeStatusFromJob("ready", "cancelled")).toBe("ready");
  });
});

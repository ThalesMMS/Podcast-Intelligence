import { describe, expect, it } from "vitest";

import { JobPanel } from "../components/job-panel";
import type { Job } from "../lib/types";
import { renderWithLocale } from "./i18n-test-utils";

const job: Job = {
  id: "job-id",
  episode_id: "episode-id",
  status: "running",
  current_step: "transcribe",
  progress: 0.5,
  error_code: null,
  error_message: null,
  started_at: null,
  completed_at: null,
  steps: [
    {
      name: "transcribe",
      ordinal: 0,
      status: "running",
      attempts: 1,
      started_at: null,
      completed_at: null,
      error_message: null,
      metrics_json: {},
    },
  ],
};

describe("job panel transcription label", () => {
  it("uses the English source label without promising diarization", () => {
    const markup = renderWithLocale(<JobPanel job={job} />);

    expect(markup).toContain("Transcribe");
    expect(markup).not.toContain("diariz");
  });

  it("localizes the transcription step to Brazilian Portuguese", () => {
    const markup = renderWithLocale(<JobPanel job={job} />, "pt-BR");

    expect(markup).toContain("Transcrever");
    expect(markup).not.toContain("diariz");
  });
});

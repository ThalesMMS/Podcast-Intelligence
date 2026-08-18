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

describe("job panel failure guidance", () => {
  it("explains how to recover when an embedding model rejects dimensions", () => {
    const markup = renderWithLocale(
      <JobPanel
        job={{
          ...job,
          status: "failed",
          current_step: "index",
          error_code: "400",
          error_message:
            "Model 'qwen3-embedding:8b' does not support Matryoshka embeddings; dimensions must be unset (received dimensions=4096).",
        }}
      />,
    );

    expect(markup).toContain("Embedding request rejected");
    expect(markup).toContain("Turn off");
    expect(markup).toContain("Send the dimensions parameter to the embedding endpoint");
  });

  it("explains how to recover from malformed Responses API JSON", () => {
    const markup = renderWithLocale(
      <JobPanel
        job={{
          ...job,
          status: "failed",
          current_step: "summarize",
          error_code: "pipeline_failed",
          error_message:
            'Invalid JSON: key must be a string at line 1 column 2 [type=json_invalid, input_value=\'{{"title":"Summary"}\']',
        }}
      />,
    );

    expect(markup).toContain("Structured summary output was invalid");
    expect(markup).toContain("Select Chat Completions under Structured-output API");
  });

  it("shows the technical message for an unclassified failure", () => {
    const markup = renderWithLocale(
      <JobPanel
        job={{
          ...job,
          status: "failed",
          error_code: "pipeline_failed",
          error_message: "Connection timed out after 120 seconds",
        }}
      />,
    );

    expect(markup).toContain("Connection timed out after 120 seconds");
  });
});

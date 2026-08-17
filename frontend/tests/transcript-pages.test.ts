import { describe, expect, it } from "vitest";

import { mergeTranscriptPages, replaceTranscriptSpeaker } from "../lib/transcript-pages";
import type { Segment, Speaker, Transcript } from "../lib/types";

const alice: Speaker = {
  id: "speaker-alice",
  label: "SPEAKER_00",
  display_name: "Alice",
  confidence: 0.9,
  attribution_method: "diarization",
  confirmed_by_user: false,
};

function segment(id: string, ordinal: number, speaker: Speaker | null = alice): Segment {
  return {
    id,
    ordinal,
    start_ms: ordinal * 1_000,
    end_ms: (ordinal + 1) * 1_000,
    text: `Segment ${ordinal}`,
    confidence: 0.9,
    language: "pt",
    speaker,
  };
}

function transcript(segments: Segment[], nextCursor: string | null): Transcript {
  return {
    id: "transcript-id",
    version: 1,
    provider: "test",
    model: null,
    language: "pt",
    segment_count: 500,
    matched_count: 500,
    limit: 2,
    query: null,
    next_cursor: nextCursor,
    anchor_segment_id: null,
    segments,
  };
}

describe("transcript pages", () => {
  it("merges pages in order without duplicating segments", () => {
    const current = transcript([segment("a", 0), segment("b", 1)], "page-2");
    const next = transcript([segment("b", 1), segment("c", 2)], null);

    const merged = mergeTranscriptPages(current, next);

    expect(merged.segments.map(({ id }) => id)).toEqual(["a", "b", "c"]);
    expect(merged.next_cursor).toBeNull();
  });

  it("updates only loaded segments belonging to the renamed speaker", () => {
    const bob = { ...alice, id: "speaker-bob", display_name: "Bob" };
    const renamed = { ...alice, display_name: "Ana", confirmed_by_user: true };
    const current = transcript([segment("a", 0), segment("b", 1, bob)], null);

    const updated = replaceTranscriptSpeaker(current, renamed);

    expect(updated?.segments[0].speaker).toEqual(renamed);
    expect(updated?.segments[1].speaker).toEqual(bob);
  });
});

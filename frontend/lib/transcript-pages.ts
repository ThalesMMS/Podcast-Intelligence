import type { Speaker, Transcript } from "./types";

export function mergeTranscriptPages(current: Transcript, next: Transcript): Transcript {
  if (current.id !== next.id || current.query !== next.query) return next;

  const knownIds = new Set(current.segments.map((segment) => segment.id));
  return {
    ...next,
    segments: [
      ...current.segments,
      ...next.segments.filter((segment) => !knownIds.has(segment.id)),
    ],
  };
}

export function replaceTranscriptSpeaker(
  transcript: Transcript | null,
  speaker: Speaker,
): Transcript | null {
  if (!transcript) return null;
  return {
    ...transcript,
    segments: transcript.segments.map((segment) =>
      segment.speaker?.id === speaker.id ? { ...segment, speaker } : segment,
    ),
  };
}

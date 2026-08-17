import type { EpisodeBrief } from "./types";

export const EPISODE_PAGE_SIZE = 50;

export type EpisodeMergeMode = "replace" | "append" | "refresh";

export function mergeEpisodePage(
  current: readonly EpisodeBrief[],
  incoming: readonly EpisodeBrief[],
  mode: EpisodeMergeMode,
): EpisodeBrief[] {
  const merged: EpisodeBrief[] = [];
  const seen = new Set<string>();
  const sources =
    mode === "append" ? [current, incoming] : mode === "refresh" ? [incoming, current] : [incoming];

  for (const source of sources) {
    for (const episode of source) {
      if (seen.has(episode.id)) continue;
      seen.add(episode.id);
      merged.push(episode);
    }
  }
  return merged;
}

export function hasMoreEpisodes(loaded: number, total: number): boolean {
  return loaded < total;
}

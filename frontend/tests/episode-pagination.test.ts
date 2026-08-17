import { describe, expect, it } from "vitest";

import { EPISODE_PAGE_SIZE, hasMoreEpisodes, mergeEpisodePage } from "../lib/episode-pagination";
import type { EpisodeBrief } from "../lib/types";

function episodes(count: number, start = 0): EpisodeBrief[] {
  return Array.from({ length: count }, (_, index) => ({
    id: String(start + index),
    title: `Episode ${start + index}`,
  })) as EpisodeBrief[];
}

describe("episode pagination", () => {
  it.each([
    [0, false],
    [1, false],
    [50, false],
  ])("handles a complete library with %i episodes", (total, expectedHasMore) => {
    const loaded = mergeEpisodePage([], episodes(total), "replace");

    expect(loaded).toHaveLength(total);
    expect(hasMoreEpisodes(loaded.length, total)).toBe(expectedHasMore);
  });

  it("loads the 51st episode without duplicating the first page", () => {
    const first = mergeEpisodePage([], episodes(EPISODE_PAGE_SIZE), "replace");
    const complete = mergeEpisodePage(first, episodes(1, EPISODE_PAGE_SIZE), "append");

    expect(first).toHaveLength(50);
    expect(hasMoreEpisodes(first.length, 51)).toBe(true);
    expect(complete.map((episode) => episode.id)).toEqual(
      episodes(51).map((episode) => episode.id),
    );
  });

  it("loads every page for a library with more than 100 episodes", () => {
    let loaded: EpisodeBrief[] = [];
    const total = 125;
    for (let offset = 0; offset < total; offset += EPISODE_PAGE_SIZE) {
      loaded = mergeEpisodePage(
        loaded,
        episodes(Math.min(EPISODE_PAGE_SIZE, total - offset), offset),
        offset === 0 ? "replace" : "append",
      );
    }

    expect(loaded).toHaveLength(total);
    expect(new Set(loaded.map((episode) => episode.id)).size).toBe(total);
    expect(hasMoreEpisodes(loaded.length, total)).toBe(false);
  });

  it("keeps loaded items stable when a new episode arrives during polling", () => {
    const current = episodes(50, 1);
    const refreshed = [episodes(1, 0)[0], ...episodes(49, 1)];

    const merged = mergeEpisodePage(current, refreshed, "refresh");

    expect(merged).toHaveLength(51);
    expect(merged[0].id).toBe("0");
    expect(new Set(merged.map((episode) => episode.id)).size).toBe(51);
  });

  it("keeps incoming items when the reported total shrinks", () => {
    const current = episodes(3, 1);
    const refreshed = [episodes(1, 0)[0], ...episodes(2, 1)];

    const merged = mergeEpisodePage(current, refreshed, "refresh");

    expect(merged.map((episode) => episode.id)).toEqual(["0", "1", "2", "3"]);
  });
});

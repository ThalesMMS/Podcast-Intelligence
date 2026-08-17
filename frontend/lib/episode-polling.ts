import type { EpisodeBrief } from "./types";

const ACTIVE_STATUSES = new Set<EpisodeBrief["status"]>(["queued", "processing"]);

export function hasActiveEpisodes(episodes: readonly EpisodeBrief[]): boolean {
  return episodes.some((episode) => ACTIVE_STATUSES.has(episode.status));
}

interface EpisodePollerOptions {
  poll: (signal: AbortSignal) => Promise<boolean>;
  isVisible: () => boolean;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

export interface EpisodePoller {
  start: () => void;
  visibilityChanged: () => void;
  stop: () => void;
}

export function createEpisodePoller({
  poll,
  isVisible,
  baseDelayMs = 5_000,
  maxDelayMs = 60_000,
}: EpisodePollerOptions): EpisodePoller {
  let stopped = true;
  let shouldPoll = true;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let request: AbortController | null = null;

  function clearScheduledPoll() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function schedule(delayMs: number) {
    if (stopped || !shouldPoll || !isVisible() || timer !== null || request !== null) return;
    timer = setTimeout(() => {
      timer = null;
      void run();
    }, delayMs);
  }

  async function run() {
    if (stopped || !shouldPoll || !isVisible() || request !== null) return;

    const controller = new AbortController();
    request = controller;
    try {
      const active = await poll(controller.signal);
      if (!controller.signal.aborted) {
        shouldPoll = active;
        failures = 0;
      }
    } catch {
      if (!controller.signal.aborted) failures += 1;
    } finally {
      if (request === controller) request = null;
    }

    if (stopped || !shouldPoll || !isVisible()) return;
    if (controller.signal.aborted) {
      schedule(0);
      return;
    }
    const delay =
      failures === 0
        ? baseDelayMs
        : Math.min(baseDelayMs * 2 ** Math.min(failures, 10), maxDelayMs);
    schedule(delay);
  }

  function start() {
    stopped = false;
    shouldPoll = true;
    failures = 0;
    clearScheduledPoll();
    schedule(0);
  }

  function visibilityChanged() {
    if (!isVisible()) {
      clearScheduledPoll();
      request?.abort();
      return;
    }
    schedule(0);
  }

  function stop() {
    stopped = true;
    shouldPoll = false;
    clearScheduledPoll();
    request?.abort();
  }

  return { start, visibilityChanged, stop };
}

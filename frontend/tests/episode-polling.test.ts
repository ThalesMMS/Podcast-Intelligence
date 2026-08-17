import { afterEach, describe, expect, it, vi } from "vitest";

import { createEpisodePoller, hasActiveEpisodes } from "../lib/episode-polling";
import type { EpisodeBrief } from "../lib/types";

describe("episode polling", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("stops after the first response when all episodes are terminal", async () => {
    vi.useFakeTimers();
    const poll = vi.fn().mockResolvedValue(false);
    const poller = createEpisodePoller({ poll, isVisible: () => true });

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(poll).toHaveBeenCalledTimes(1);
    poller.stop();
  });

  it("polls active episodes and stops when they become terminal", async () => {
    vi.useFakeTimers();
    const poll = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(false);
    const poller = createEpisodePoller({ poll, isVisible: () => true });

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(4_999);
    expect(poll).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(poll).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(poll).toHaveBeenCalledTimes(2);
    poller.stop();
  });

  it("pauses while hidden and resumes immediately when visible", async () => {
    vi.useFakeTimers();
    let visible = false;
    const poll = vi.fn().mockResolvedValue(true);
    const poller = createEpisodePoller({ poll, isVisible: () => visible });

    poller.start();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(poll).not.toHaveBeenCalled();

    visible = true;
    poller.visibilityChanged();
    await vi.advanceTimersByTimeAsync(0);
    expect(poll).toHaveBeenCalledTimes(1);

    visible = false;
    poller.visibilityChanged();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(poll).toHaveBeenCalledTimes(1);
    poller.stop();
  });

  it("cancels an in-flight request and ignores its stale result", async () => {
    vi.useFakeTimers();
    let visible = true;
    let resolveFirst: ((active: boolean) => void) | undefined;
    let firstSignal: AbortSignal | undefined;
    const appliedResults: string[] = [];
    const first = new Promise<boolean>((resolve) => {
      resolveFirst = resolve;
    });
    const poll = vi
      .fn()
      .mockImplementationOnce((signal: AbortSignal) => {
        firstSignal = signal;
        return first.then((active) => {
          if (!signal.aborted) appliedResults.push("stale");
          return active;
        });
      })
      .mockImplementationOnce(() => {
        appliedResults.push("fresh");
        return Promise.resolve(false);
      });
    const poller = createEpisodePoller({ poll, isVisible: () => visible });

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    visible = false;
    poller.visibilityChanged();
    expect(firstSignal?.aborted).toBe(true);

    resolveFirst?.(false);
    await vi.advanceTimersByTimeAsync(0);
    visible = true;
    poller.visibilityChanged();
    await vi.advanceTimersByTimeAsync(0);

    expect(poll).toHaveBeenCalledTimes(2);
    expect(appliedResults).toEqual(["fresh"]);
    poller.stop();
  });

  it("never overlaps requests even when a poll takes longer than the interval", async () => {
    vi.useFakeTimers();
    let resolveFirst: ((active: boolean) => void) | undefined;
    const first = new Promise<boolean>((resolve) => {
      resolveFirst = resolve;
    });
    const poll = vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce(false);
    const poller = createEpisodePoller({ poll, isVisible: () => true });

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(poll).toHaveBeenCalledTimes(1);

    resolveFirst?.(true);
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(poll).toHaveBeenCalledTimes(2);
    poller.stop();
  });

  it("backs off after consecutive failures", async () => {
    vi.useFakeTimers();
    const poll = vi
      .fn()
      .mockRejectedValueOnce(new Error("first"))
      .mockRejectedValueOnce(new Error("second"))
      .mockResolvedValueOnce(false);
    const poller = createEpisodePoller({ poll, isVisible: () => true });

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(9_999);
    expect(poll).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(poll).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(19_999);
    expect(poll).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(poll).toHaveBeenCalledTimes(3);
    poller.stop();
  });

  it("retries immediately when restarted during backoff", async () => {
    vi.useFakeTimers();
    const poll = vi.fn().mockRejectedValueOnce(new Error("first")).mockResolvedValueOnce(false);
    const poller = createEpisodePoller({ poll, isVisible: () => true });

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(poll).toHaveBeenCalledTimes(1);

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(poll).toHaveBeenCalledTimes(2);
    poller.stop();
  });

  it("recognizes only queued and processing episodes as active", () => {
    const episode = (status: EpisodeBrief["status"]) => ({ status }) as EpisodeBrief;

    expect(hasActiveEpisodes([episode("queued")])).toBe(true);
    expect(hasActiveEpisodes([episode("processing")])).toBe(true);
    expect(hasActiveEpisodes([episode("ready"), episode("failed")])).toBe(false);
  });
});

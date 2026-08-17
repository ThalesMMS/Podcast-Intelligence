import { afterEach, describe, expect, it, vi } from "vitest";

import {
  playbackRefreshDelay,
  PLAYBACK_REFRESH_RETRY_MS,
  replacePlaybackSource,
  shouldRefreshPlayback,
} from "../lib/playback";

class FakeAudio {
  currentTime = 0;
  paused = true;
  src = "https://media.example/expired";
  load = vi.fn(() => {
    this.paused = true;
  });
  play = vi.fn().mockImplementation(async () => {
    this.paused = false;
  });
  private listeners = new Map<string, Set<EventListenerOrEventListenerObject>>();

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string) {
    for (const listener of this.listeners.get(type) ?? []) {
      if (typeof listener === "function") listener(new Event(type));
      else listener.handleEvent(new Event(type));
    }
  }
}

afterEach(() => {
  vi.useRealTimers();
});

describe("playback expiration", () => {
  it("renews expired and nearly expired URLs while preserving fresh URLs", () => {
    const now = Date.parse("2026-07-26T20:00:00Z");

    expect(shouldRefreshPlayback("2026-07-26T19:59:59Z", now)).toBe(true);
    expect(shouldRefreshPlayback("2026-07-26T20:00:30Z", now)).toBe(true);
    expect(shouldRefreshPlayback("2026-07-26T20:02:00Z", now)).toBe(false);
    expect(playbackRefreshDelay("2026-07-26T20:02:00Z", now)).toBe(60_000);
    expect(playbackRefreshDelay(null, now)).toBe(PLAYBACK_REFRESH_RETRY_MS);
    expect(playbackRefreshDelay("invalid", now)).toBe(PLAYBACK_REFRESH_RETRY_MS);
  });

  it("reopens renewed media at the previous range and resumes playback", async () => {
    const player = new FakeAudio();
    const replacement = replacePlaybackSource(
      player as unknown as HTMLAudioElement,
      "https://media.example/renewed",
      { positionSeconds: 42.5, resume: true },
    );

    expect(player.src).toBe("https://media.example/renewed");
    expect(player.load).toHaveBeenCalledOnce();
    player.emit("loadedmetadata");
    await replacement;

    expect(player.currentTime).toBe(42.5);
    expect(player.play).toHaveBeenCalledOnce();
  });

  it("applies the latest seek requested while renewal is in flight", async () => {
    const player = new FakeAudio();
    let request = { positionSeconds: 10, resume: false };
    const replacement = replacePlaybackSource(
      player as unknown as HTMLAudioElement,
      "https://media.example/renewed",
      request,
      { getRequest: () => request },
    );

    request = { positionSeconds: 84, resume: true };
    player.emit("loadedmetadata");
    await replacement;

    expect(player.currentTime).toBe(84);
    expect(player.play).toHaveBeenCalledOnce();
  });

  it("rejects when renewal is aborted", async () => {
    const player = new FakeAudio();
    player.currentTime = 18;
    const controller = new AbortController();
    const replacement = replacePlaybackSource(
      player as unknown as HTMLAudioElement,
      "https://media.example/renewed",
      { positionSeconds: 0, resume: false },
      { signal: controller.signal },
    );

    controller.abort();

    await expect(replacement).rejects.toMatchObject({ name: "AbortError" });
    expect(player.src).toBe("https://media.example/expired");
    expect(player.currentTime).toBe(18);
    expect(player.load).toHaveBeenCalledTimes(2);
  });

  it("rejects when the renewed source emits an error", async () => {
    const player = new FakeAudio();
    player.currentTime = 24;
    const replacement = replacePlaybackSource(
      player as unknown as HTMLAudioElement,
      "https://media.example/renewed",
      { positionSeconds: 0, resume: false },
    );

    player.emit("error");

    await expect(replacement).rejects.toMatchObject({ code: "playback_replacement_failed" });
    expect(player.src).toBe("https://media.example/expired");
    expect(player.currentTime).toBe(24);
    expect(player.load).toHaveBeenCalledTimes(2);
  });

  it("restores the previous playing state when renewal fails", async () => {
    const player = new FakeAudio();
    player.currentTime = 27;
    player.paused = false;
    const replacement = replacePlaybackSource(
      player as unknown as HTMLAudioElement,
      "https://media.example/renewed",
      { positionSeconds: 0, resume: true },
    );

    expect(player.paused).toBe(true);
    player.emit("error");

    await expect(replacement).rejects.toMatchObject({ code: "playback_replacement_failed" });
    expect(player.src).toBe("https://media.example/expired");
    expect(player.currentTime).toBe(27);
    expect(player.play).toHaveBeenCalledOnce();
    expect(player.paused).toBe(false);
  });

  it("times out when the renewed source never loads", async () => {
    vi.useFakeTimers();
    const player = new FakeAudio();
    player.currentTime = 30;
    const replacement = replacePlaybackSource(
      player as unknown as HTMLAudioElement,
      "https://media.example/renewed",
      { positionSeconds: 0, resume: false },
      { timeoutMs: 100 },
    );
    const rejection = expect(replacement).rejects.toMatchObject({
      code: "playback_replacement_failed",
    });

    await vi.advanceTimersByTimeAsync(100);

    await rejection;
    expect(player.src).toBe("https://media.example/expired");
    expect(player.currentTime).toBe(30);
    expect(player.load).toHaveBeenCalledTimes(2);
  });

  it("keeps renewal successful when autoplay is blocked", async () => {
    const player = new FakeAudio();
    player.play.mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));
    const replacement = replacePlaybackSource(
      player as unknown as HTMLAudioElement,
      "https://media.example/renewed",
      { positionSeconds: 0, resume: true },
    );

    player.emit("loadedmetadata");

    await expect(replacement).resolves.toBeUndefined();
  });
});

import { ClientError } from "@/lib/errors";

export const PLAYBACK_REFRESH_LEEWAY_MS = 60_000;
export const PLAYBACK_REFRESH_RETRY_MS = 60_000;

export function shouldRefreshPlayback(
  expiresAt: string | null,
  now = Date.now(),
  leewayMs = PLAYBACK_REFRESH_LEEWAY_MS,
) {
  if (!expiresAt) return true;
  const expiresAtMs = Date.parse(expiresAt);
  return !Number.isFinite(expiresAtMs) || expiresAtMs - now <= leewayMs;
}

export function playbackRefreshDelay(
  expiresAt: string | null,
  now = Date.now(),
  leewayMs = PLAYBACK_REFRESH_LEEWAY_MS,
) {
  if (!expiresAt) return PLAYBACK_REFRESH_RETRY_MS;
  const expiresAtMs = Date.parse(expiresAt);
  if (!Number.isFinite(expiresAtMs)) return PLAYBACK_REFRESH_RETRY_MS;
  return Math.max(0, expiresAtMs - now - leewayMs);
}

export interface PlaybackRequest {
  positionSeconds: number;
  resume: boolean;
}

interface PlaybackReplacementOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  getRequest?: () => PlaybackRequest;
}

export function replacePlaybackSource(
  player: HTMLAudioElement,
  url: string,
  request: PlaybackRequest,
  { signal, timeoutMs = 15_000, getRequest }: PlaybackReplacementOptions = {},
): Promise<void> {
  return new Promise((resolve, reject) => {
    const previousSource = player.currentSrc || player.src;
    const previousTime = player.currentTime;
    const previousWasPlaying = !player.paused;
    let sourceWasReplaced = false;
    let settled = false;
    const timer = setTimeout(() => {
      rejectReplacement(new ClientError("playback_replacement_failed"));
    }, timeoutMs);

    function cleanup() {
      clearTimeout(timer);
      player.removeEventListener("loadedmetadata", handleLoadedMetadata);
      player.removeEventListener("error", handleError);
      signal?.removeEventListener("abort", handleAbort);
    }

    function restorePreviousSource() {
      if (!sourceWasReplaced) return;
      player.src = previousSource;
      player.load();
      if (Number.isFinite(previousTime) && previousTime >= 0) {
        try {
          player.currentTime = previousTime;
        } catch {
          // Some browsers defer seeks until metadata for the restored source is available.
        }
      }
      if (previousWasPlaying) {
        void player.play().catch(() => undefined);
      }
    }

    function rejectReplacement(error: Error | DOMException) {
      if (settled) return;
      settled = true;
      cleanup();
      restorePreviousSource();
      reject(error);
    }

    function handleAbort() {
      rejectReplacement(new DOMException("Playback renewal was aborted", "AbortError"));
    }

    function handleError() {
      rejectReplacement(new ClientError("playback_replacement_failed"));
    }

    function handleLoadedMetadata() {
      if (settled) return;
      settled = true;
      cleanup();
      const latestRequest = getRequest?.() ?? request;
      if (Number.isFinite(latestRequest.positionSeconds) && latestRequest.positionSeconds > 0) {
        player.currentTime = latestRequest.positionSeconds;
      }
      if (latestRequest.resume) {
        void player.play().catch(() => undefined);
      }
      resolve();
    }

    if (signal?.aborted) {
      handleAbort();
      return;
    }
    player.addEventListener("loadedmetadata", handleLoadedMetadata);
    player.addEventListener("error", handleError);
    signal?.addEventListener("abort", handleAbort, { once: true });
    player.src = url;
    sourceWasReplaced = true;
    player.load();
  });
}

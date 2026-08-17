"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ChatView } from "@/components/chat-view";
import {
  ChevronLeftIcon,
  DownloadIcon,
  ExternalIcon,
  MessageIcon,
  SummaryIcon,
  TranscriptIcon,
} from "@/components/icons";
import { JobPanel } from "@/components/job-panel";
import { StatusBadge } from "@/components/status-badge";
import { SummaryView } from "@/components/summary-view";
import { TranscriptView } from "@/components/transcript-view";
import { API_BASE_URL, api } from "@/lib/api";
import { createEpisodePoller } from "@/lib/episode-polling";
import { localizeError } from "@/lib/errors";
import { formatDuration } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useI18n } from "@/lib/i18n/provider";
import {
  playbackRefreshDelay,
  type PlaybackRequest,
  replacePlaybackSource,
  shouldRefreshPlayback,
} from "@/lib/playback";
import { episodeStatusFromJob, getWorkspaceRefreshPlan } from "@/lib/workspace-polling";
import type { EpisodeDetail, Job, Transcript } from "@/lib/types";

type Tab = "summary" | "transcript" | "chat";

interface PlaybackRenewalOptions {
  automatic?: boolean;
  resume?: boolean;
  seekSeconds?: number;
}

interface WorkspaceError {
  cause: unknown;
  fallback: MessageKey;
}

export function EpisodeWorkspace({ episodeId }: { episodeId: string }) {
  const { formatDate, t } = useI18n();
  const [episode, setEpisode] = useState<EpisodeDetail | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown | null>(null);
  const [pollWarning, setPollWarning] = useState<unknown | null>(null);
  const [playbackError, setPlaybackError] = useState<WorkspaceError | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const latestJob = useRef<Job | null>(null);
  const playbackExpiresAt = useRef<string | null>(null);
  const playbackRenewal = useRef<Promise<void> | null>(null);
  const playbackRenewalRequest = useRef<PlaybackRequest | null>(null);
  const playbackAbort = useRef<AbortController | null>(null);
  const playbackRequested = useRef(false);
  const playbackPauseIsRenewal = useRef(false);
  const automaticRecoveryUsed = useRef(false);
  const workspaceAbort = useRef<AbortController | null>(null);

  const refreshTranscript = useCallback(
    async (signal?: AbortSignal) => {
      const next = await api.getTranscript(episodeId, { signal });
      if (!signal?.aborted) setTranscript(next);
      return next;
    },
    [episodeId],
  );

  const refreshEpisode = useCallback(
    async (signal?: AbortSignal) => {
      const next = await api.getEpisode(episodeId, { signal });
      if (!signal?.aborted) {
        setEpisode(next);
        latestJob.current = next.latest_job;
        playbackExpiresAt.current = next.playback_expires_at;
      }
      return next;
    },
    [episodeId],
  );

  const renewPlayback = useCallback(
    (options: PlaybackRenewalOptions = {}) => {
      const player = audioRef.current;
      const request = {
        positionSeconds: options.seekSeconds ?? player?.currentTime ?? 0,
        resume: options.resume ?? Boolean(player && !player.paused),
      };
      playbackRenewalRequest.current = request;
      if (playbackRenewal.current) return playbackRenewal.current;

      const controller = new AbortController();
      playbackAbort.current = controller;
      const renewal = (async () => {
        try {
          const access = await api.getPlayback(episodeId, { signal: controller.signal });
          if (controller.signal.aborted) return;
          if (player) {
            await replacePlaybackSource(player, access.playback_url, request, {
              signal: controller.signal,
              getRequest: () => playbackRenewalRequest.current ?? request,
            });
          }
          if (controller.signal.aborted) return;
          playbackExpiresAt.current = access.expires_at;
          setEpisode((current) =>
            current
              ? {
                  ...current,
                  playback_expires_at: access.expires_at,
                }
              : current,
          );
          setPlaybackError(null);
          automaticRecoveryUsed.current = false;
        } catch (cause) {
          if (!controller.signal.aborted) {
            setPlaybackError({ cause, fallback: "errors.playbackRenew" });
          }
          throw cause;
        } finally {
          if (playbackAbort.current === controller) playbackAbort.current = null;
          playbackRenewalRequest.current = null;
        }
      })();
      playbackRenewal.current = renewal;
      const clearRenewal = () => {
        if (playbackRenewal.current === renewal) playbackRenewal.current = null;
      };
      void renewal.then(clearRenewal, clearRenewal);
      return renewal;
    },
    [episodeId],
  );

  useEffect(
    () => () => {
      playbackAbort.current?.abort();
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    workspaceAbort.current = controller;
    async function initialLoad() {
      setLoading(true);
      try {
        const next = await refreshEpisode(controller.signal);
        if (controller.signal.aborted) return;
        setError(null);
        if (
          next.status === "ready" ||
          next.latest_job?.steps.some(
            (step) => step.name === "transcribe" && step.status === "completed",
          )
        ) {
          await refreshTranscript(controller.signal).catch(() => undefined);
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void initialLoad();
    return () => {
      if (workspaceAbort.current === controller) workspaceAbort.current = null;
      controller.abort();
    };
  }, [refreshEpisode, refreshTranscript]);

  const polledJobId = episode?.latest_job?.id;
  useEffect(() => {
    if (!polledJobId) return;
    const controller = createEpisodePoller({
      isVisible: () => document.visibilityState === "visible",
      poll: async (signal) => {
        try {
          const job = await api.getJob(polledJobId, { signal });
          if (signal.aborted) return true;
          const plan = getWorkspaceRefreshPlan(latestJob.current, job);
          setEpisode((current) =>
            current
              ? {
                  ...current,
                  latest_job: job,
                  status: episodeStatusFromJob(current.status, job.status),
                }
              : current,
          );
          if (plan.refreshTranscript) await refreshTranscript(signal);
          let observedJob = job;
          if (plan.refreshEpisode) {
            const detail = await refreshEpisode(signal);
            observedJob = detail.latest_job ?? job;
          }
          if (!signal.aborted) {
            latestJob.current = observedJob;
            setPollWarning(null);
          }
          return plan.continuePolling;
        } catch (cause) {
          if (!signal.aborted) {
            setPollWarning(cause);
          }
          throw cause;
        }
      },
    });
    const handleVisibilityChange = () => controller.visibilityChanged();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    controller.start();
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      controller.stop();
    };
  }, [polledJobId, refreshEpisode, refreshTranscript]);

  useEffect(() => {
    if (!episode?.playback_url) return;

    const refresh = () => {
      const player = audioRef.current;
      void renewPlayback({ resume: Boolean(player && !player.paused) }).catch(() => undefined);
    };
    const timer = window.setTimeout(refresh, playbackRefreshDelay(episode.playback_expires_at));
    const handleVisibilityChange = () => {
      if (
        document.visibilityState === "visible" &&
        shouldRefreshPlayback(playbackExpiresAt.current)
      ) {
        refresh();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [episode?.playback_expires_at, episode?.playback_url, renewPlayback]);

  function pauseForPlaybackRenewal(player: HTMLAudioElement, options: PlaybackRenewalOptions) {
    playbackPauseIsRenewal.current = true;
    player.pause();
    void renewPlayback(options)
      .catch(() => undefined)
      .finally(() => {
        playbackPauseIsRenewal.current = false;
      });
  }

  function seek(milliseconds: number) {
    const player = audioRef.current;
    if (!player) return;
    playbackRequested.current = true;
    const positionSeconds = milliseconds / 1000;
    player.scrollIntoView({ behavior: "smooth", block: "center" });
    if (shouldRefreshPlayback(playbackExpiresAt.current)) {
      pauseForPlaybackRenewal(player, { resume: true, seekSeconds: positionSeconds });
      return;
    }
    player.currentTime = positionSeconds;
    void player.play().catch(() => undefined);
  }

  function handlePlaybackPlay() {
    playbackRequested.current = true;
    if (!shouldRefreshPlayback(playbackExpiresAt.current)) return;
    const player = audioRef.current;
    if (!player) return;
    pauseForPlaybackRenewal(player, { resume: true });
  }

  function handlePlaybackSeeking() {
    const player = audioRef.current;
    if (!player || !shouldRefreshPlayback(playbackExpiresAt.current)) return;
    const resume = !player.paused;
    playbackRequested.current = resume;
    const positionSeconds = player.currentTime;
    pauseForPlaybackRenewal(player, { resume, seekSeconds: positionSeconds });
  }

  function handlePlaybackError() {
    if (playbackRenewal.current) return;
    if (automaticRecoveryUsed.current) {
      setPlaybackError({
        cause: new Error("Playback recovery was already attempted"),
        fallback: "errors.playbackLoad",
      });
      return;
    }
    automaticRecoveryUsed.current = true;
    const player = audioRef.current;
    void renewPlayback({
      automatic: true,
      resume: playbackRequested.current,
      seekSeconds: player?.currentTime,
    }).catch(() => undefined);
  }

  function retryPlayback() {
    automaticRecoveryUsed.current = false;
    playbackRequested.current = true;
    void renewPlayback({ resume: true }).catch(() => undefined);
  }

  if (loading) return <EpisodeSkeleton />;
  if (error || !episode) {
    return (
      <div className="page centeredPage">
        <div className="notice errorNotice">
          <strong>{t("workspace.openFailureTitle")}</strong>
          <span>
            {error ? localizeError(error, t, "errors.episodeOpen") : t("workspace.episodeNotFound")}
          </span>
          <Link href="/">{t("workspace.backToLibrary")}</Link>
        </div>
      </div>
    );
  }

  const summary = episode.summaries[0] ?? null;
  const readyForChat = episode.status === "ready" && Boolean(transcript);
  return (
    <div className="page episodePage">
      <header className="episodeHeader">
        <Link className="backLink" href="/">
          <ChevronLeftIcon size={17} /> {t("workspace.library")}
        </Link>
        <div className="episodeHero">
          {episode.artwork_url ? (
            <img alt="" className="heroArtwork" src={episode.artwork_url} />
          ) : (
            <div className="heroArtwork artworkFallback">
              <span>{episode.title.slice(0, 1).toUpperCase()}</span>
            </div>
          )}
          <div className="heroCopy">
            <div className="heroStatus">
              <StatusBadge status={episode.status} />
            </div>
            <p className="episodeShow">{episode.show?.title ?? t("workspace.importedAudio")}</p>
            <h1>{episode.title}</h1>
            <div className="heroMeta">
              <span>{formatDate(episode.published_at ?? episode.created_at)}</span>
              <span>{formatDuration(episode.duration_ms)}</span>
              {episode.language ? <span>{episode.language.toUpperCase()}</span> : null}
              {episode.canonical_url ? (
                <a href={episode.canonical_url} rel="noreferrer" target="_blank">
                  {t("workspace.source")} <ExternalIcon size={14} />
                </a>
              ) : null}
            </div>
          </div>
        </div>
        {episode.playback_url ? (
          <div className="audioSurface">
            <audio
              controls
              onEnded={() => {
                playbackRequested.current = false;
              }}
              onError={handlePlaybackError}
              onPause={() => {
                if (!playbackPauseIsRenewal.current) playbackRequested.current = false;
              }}
              onPlay={handlePlaybackPlay}
              onSeeking={handlePlaybackSeeking}
              preload="metadata"
              ref={audioRef}
              src={episode.playback_url}
            />
            {playbackError ? (
              <div className="playbackError" role="alert">
                <span>{localizeError(playbackError.cause, t, playbackError.fallback)}</span>
                <button onClick={retryPlayback} type="button">
                  {t("workspace.renewAudio")}
                </button>
              </div>
            ) : null}
            <div className="exportMenu">
              <span>{t("workspace.export")}</span>
              {(["markdown", "json", "srt", "vtt"] as const).map((format) => (
                <a
                  href={`${API_BASE_URL}/v1/episodes/${episode.id}/exports/${format}`}
                  key={format}
                >
                  <DownloadIcon size={14} /> {format.toUpperCase()}
                </a>
              ))}
            </div>
          </div>
        ) : null}
      </header>

      {pollWarning ? (
        <div className="notice warningNotice workspacePollWarning" role="status">
          <strong>{t("workspace.staleTitle")}</strong>
          <span>{localizeError(pollWarning, t, "errors.workspaceRefresh")}</span>
        </div>
      ) : null}

      <div className="episodeLayout">
        <div className="artifactWorkspace">
          <nav className="artifactTabs" aria-label={t("workspace.artifacts")}>
            <button
              className={tab === "summary" ? "active" : ""}
              onClick={() => setTab("summary")}
              type="button"
            >
              <SummaryIcon size={18} /> {t("workspace.summaryTab")}
            </button>
            <button
              className={tab === "transcript" ? "active" : ""}
              onClick={() => setTab("transcript")}
              type="button"
            >
              <TranscriptIcon size={18} /> {t("workspace.transcriptTab")}
            </button>
            <button
              className={tab === "chat" ? "active" : ""}
              onClick={() => setTab("chat")}
              type="button"
            >
              <MessageIcon size={18} /> {t("workspace.chatTab")}
            </button>
          </nav>
          <div className="artifactContent">
            {tab === "summary" ? (
              <SummaryView
                episodeId={episode.id}
                onGenerated={async () => {
                  await refreshEpisode(workspaceAbort.current?.signal);
                }}
                onSeek={seek}
                summary={summary}
              />
            ) : null}
            {tab === "transcript" ? (
              <TranscriptView episodeId={episode.id} onSeek={seek} transcript={transcript} />
            ) : null}
            {tab === "chat" ? (
              <ChatView episodeId={episode.id} onSeek={seek} ready={readyForChat} />
            ) : null}
          </div>
        </div>
        <JobPanel job={episode.latest_job} />
      </div>
    </div>
  );
}

function EpisodeSkeleton() {
  return (
    <div className="page episodePage">
      <div className="skeleton skeletonBack" />
      <div className="episodeHero">
        <div className="heroArtwork skeleton" />
        <div className="heroCopy">
          <div className="skeleton skeletonTitle wide" />
          <div className="skeleton skeletonText" />
          <div className="skeleton skeletonText short" />
        </div>
      </div>
      <div className="episodeLayout">
        <div className="artifactWorkspace skeletonPanel" />
        <div className="jobPanel skeletonPanel" />
      </div>
    </div>
  );
}

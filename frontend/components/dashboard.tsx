"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { ArrowIcon, ClockIcon, LinkIcon, SparkIcon, UploadIcon } from "@/components/icons";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import { EPISODE_PAGE_SIZE, hasMoreEpisodes, mergeEpisodePage } from "@/lib/episode-pagination";
import { createEpisodePoller, type EpisodePoller } from "@/lib/episode-polling";
import { ClientError, localizeError } from "@/lib/errors";
import { excerpt, formatDuration } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { getNextTabIndex } from "@/lib/tabs";
import type { EpisodeBrief } from "@/lib/types";

type ImportMode = "file" | "url";
type SourceType = "direct_url" | "rss" | "apple" | "spotify";
const importModes: ImportMode[] = ["file", "url"];

export function Dashboard() {
  const router = useRouter();
  const { formatDate, formatNumber, t, tp } = useI18n();
  const [episodes, setEpisodes] = useState<EpisodeBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<unknown | null>(null);
  const [mode, setMode] = useState<ImportMode>("file");
  const [sourceType, setSourceType] = useState<SourceType>("rss");
  const [url, setUrl] = useState("");
  const [episodeTitle, setEpisodeTitle] = useState("");
  const [rssUrlHint, setRssUrlHint] = useState("");
  const [language, setLanguage] = useState("pt");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const modeTabs = useRef<Record<ImportMode, HTMLButtonElement | null>>({
    file: null,
    url: null,
  });
  const poller = useRef<EpisodePoller | null>(null);
  const loadedCount = useRef(0);
  const paginationRequest = useRef<AbortController | null>(null);

  const loadEpisodes = useCallback(async (signal: AbortSignal, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const response = await api.listEpisodes({
        limit: Math.max(EPISODE_PAGE_SIZE, loadedCount.current),
        offset: 0,
        signal,
      });
      if (signal.aborted) return false;
      setEpisodes((current) => {
        const merged = mergeEpisodePage(current, response.items, silent ? "refresh" : "replace");
        loadedCount.current = merged.length;
        return merged;
      });
      setTotal(response.total);
      setLoadError(null);
      return response.active_count > 0;
    } catch (error) {
      if (signal.aborted) throw error;
      if (!silent) {
        setLoadError(error);
      }
      throw error;
    } finally {
      if (!silent && !signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let initialLoad = true;
    const controller = createEpisodePoller({
      isVisible: () => document.visibilityState === "visible",
      poll: async (signal) => {
        try {
          const active = await loadEpisodes(signal, !initialLoad);
          if (!signal.aborted) initialLoad = false;
          return active;
        } catch (error) {
          if (!signal.aborted) initialLoad = false;
          throw error;
        }
      },
    });
    poller.current = controller;
    const handleVisibilityChange = () => controller.visibilityChanged();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    controller.start();
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      controller.stop();
      paginationRequest.current?.abort();
      poller.current = null;
    };
  }, [loadEpisodes]);

  async function handleLoadMore() {
    if (loadingMore || !hasMoreEpisodes(loadedCount.current, total)) return;
    const controller = new AbortController();
    paginationRequest.current?.abort();
    paginationRequest.current = controller;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const response = await api.listEpisodes({
        limit: EPISODE_PAGE_SIZE,
        offset: loadedCount.current,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setEpisodes((current) => {
        const merged = mergeEpisodePage(current, response.items, "append");
        loadedCount.current = merged.length;
        return merged;
      });
      setTotal(response.total);
      if (response.active_count > 0) poller.current?.start();
    } catch (error) {
      if (!controller.signal.aborted) {
        setLoadMoreError(error);
      }
    } finally {
      if (paginationRequest.current === controller) paginationRequest.current = null;
      if (!controller.signal.aborted) setLoadingMore(false);
    }
  }

  async function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      let result: { episode_id: string; job_id: string };
      if (mode === "file") {
        if (!file) throw new ClientError("media_required");
        const upload = await api.initiateUpload(file);
        await api.uploadObject(upload.upload_url, upload.fields, file);
        result = await api.createUploadImport(upload.object_key, file, language);
      } else {
        if (!url.trim()) throw new ClientError("source_url_required");
        result = await api.createUrlImport(
          sourceType,
          url.trim(),
          episodeTitle.trim(),
          language,
          rssUrlHint.trim(),
        );
      }
      router.push(`/episodes/${result.episode_id}`);
    } catch (error) {
      setSubmitError(error);
    } finally {
      setSubmitting(false);
    }
  }

  function handleModeKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentMode: ImportMode) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const nextIndex = getNextTabIndex(
      importModes.indexOf(currentMode),
      event.key,
      importModes.length,
    );
    if (nextIndex === null) return;
    event.preventDefault();
    const nextMode = importModes[nextIndex];
    setMode(nextMode);
    modeTabs.current[nextMode]?.focus();
  }

  return (
    <div className="page dashboardPage">
      <header className="pageHeader dashboardHeader">
        <div>
          <h1>{t("dashboard.title")}</h1>
          <p>{t("dashboard.subtitle")}</p>
        </div>
        <div
          className="headerMetric"
          aria-label={tp("dashboard.episodeCount", total, { count: formatNumber(total) })}
        >
          <strong>{formatNumber(total)}</strong>
          <span>{tp("dashboard.episodeLabel", total)}</span>
        </div>
      </header>

      <section className="importSurface" aria-labelledby="import-title">
        <div className="importIntro">
          <span className="sectionIcon">
            <SparkIcon size={20} />
          </span>
          <div>
            <h2 id="import-title">{t("dashboard.newAnalysis")}</h2>
            <p>{t("dashboard.importIntro")}</p>
          </div>
        </div>
        <div
          className="modeSwitch"
          role="tablist"
          aria-label={t("dashboard.importType")}
          aria-orientation="horizontal"
        >
          {importModes.map((candidate) => (
            <button
              aria-controls={`import-panel-${candidate}`}
              aria-selected={mode === candidate}
              className={mode === candidate ? "modeButton active" : "modeButton"}
              id={`import-tab-${candidate}`}
              key={candidate}
              onClick={() => setMode(candidate)}
              onKeyDown={(event) => handleModeKeyDown(event, candidate)}
              ref={(element) => {
                modeTabs.current[candidate] = element;
              }}
              role="tab"
              tabIndex={mode === candidate ? 0 : -1}
              type="button"
            >
              {candidate === "file" ? <UploadIcon size={18} /> : <LinkIcon size={18} />}
              {candidate === "file" ? ` ${t("dashboard.file")}` : ` ${t("dashboard.linkOrRss")}`}
            </button>
          ))}
        </div>

        <form className="importForm" onSubmit={handleImport}>
          <div
            aria-labelledby="import-tab-file"
            className="importPanel"
            hidden={mode !== "file"}
            id="import-panel-file"
            role="tabpanel"
          >
            <button
              className={file ? "dropField hasFile" : "dropField"}
              onClick={() => fileInput.current?.click()}
              type="button"
            >
              <input
                accept="audio/*,video/*"
                hidden
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                ref={fileInput}
                type="file"
              />
              <span className="dropIcon">
                <UploadIcon size={24} />
              </span>
              <span className="dropCopy">
                <strong>{file ? file.name : t("dashboard.chooseMedia")}</strong>
                <small>
                  {file
                    ? `${formatNumber(Math.round((file.size / 1024 / 1024) * 10) / 10)} MB`
                    : t("dashboard.directUpload")}
                </small>
              </span>
            </button>
          </div>
          <div
            aria-labelledby="import-tab-url"
            className="importPanel"
            hidden={mode !== "url"}
            id="import-panel-url"
            role="tabpanel"
          >
            <div className="urlFields">
              <label className="field compactField">
                <span>{t("dashboard.source")}</span>
                <select
                  value={sourceType}
                  onChange={(event) => {
                    setSourceType(event.target.value as SourceType);
                    setRssUrlHint("");
                  }}
                >
                  <option value="rss">Feed RSS</option>
                  <option value="apple">Apple Podcasts</option>
                  <option value="spotify">Spotify</option>
                  <option value="direct_url">{t("dashboard.directMediaUrl")}</option>
                </select>
              </label>
              <label className="field urlField">
                <span>URL</span>
                <input
                  inputMode="url"
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://…"
                  type="url"
                  value={url}
                />
              </label>
              <label className="field titleField">
                <span>
                  {t("dashboard.specificEpisode")} <em>{t("dashboard.optional")}</em>
                </span>
                <input
                  onChange={(event) => setEpisodeTitle(event.target.value)}
                  placeholder={t("dashboard.episodeTitlePlaceholder")}
                  type="text"
                  value={episodeTitle}
                />
              </label>
              <label
                className="field rssHintField"
                hidden={sourceType !== "spotify" && sourceType !== "apple"}
              >
                <span>
                  {t("dashboard.rssHint")} <em>{t("dashboard.optional")}</em>
                </span>
                <input
                  id="rss-url-hint"
                  inputMode="url"
                  onChange={(event) => setRssUrlHint(event.target.value)}
                  placeholder={t("dashboard.rssPlaceholder")}
                  type="url"
                  value={rssUrlHint}
                />
              </label>
            </div>
          </div>
          <div className="importFooter">
            <label className="field languageField">
              <span>{t("dashboard.language")}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                <option value="pt">{t("dashboard.languagePortuguese")}</option>
                <option value="en">{t("dashboard.languageEnglish")}</option>
                <option value="es">{t("dashboard.languageSpanish")}</option>
                <option value="">{t("dashboard.languageAuto")}</option>
              </select>
            </label>
            <div className="importAction">
              {submitError ? (
                <p className="formError">{localizeError(submitError, t, "errors.importStart")}</p>
              ) : null}
              <button className="primaryButton" disabled={submitting} type="submit">
                {submitting ? t("dashboard.preparing") : t("dashboard.startProcessing")}
                <ArrowIcon size={18} />
              </button>
            </div>
          </div>
        </form>
      </section>

      <section className="librarySection" aria-labelledby="library-title">
        <div className="sectionHeading">
          <div>
            <h2 id="library-title">{t("dashboard.episodesTitle")}</h2>
            <p>{t("dashboard.episodesHint")}</p>
          </div>
        </div>

        {loading ? <LibrarySkeleton /> : null}
        {!loading && loadError ? (
          <div className="notice errorNotice">
            <strong>{t("dashboard.libraryFailure")}</strong>
            <span>{localizeError(loadError, t, "errors.libraryLoad")}</span>
            <button onClick={() => poller.current?.start()} type="button">
              {t("common.retry")}
            </button>
          </div>
        ) : null}
        {!loading && !loadError && episodes.length === 0 ? <EmptyLibrary /> : null}
        {!loading && !loadError && episodes.length > 0 ? (
          <>
            <div className="episodeList">
              {episodes.map((episode) => (
                <Link className="episodeRow" href={`/episodes/${episode.id}`} key={episode.id}>
                  <EpisodeArtwork episode={episode} />
                  <div className="episodeCopy">
                    <div className="episodeTitleLine">
                      <h3>{episode.title}</h3>
                      <StatusBadge status={episode.status} />
                    </div>
                    <p className="episodeShow">
                      {episode.show?.title ?? t("dashboard.importedAudio")}
                    </p>
                    <p className="episodeDescription">
                      {excerpt(episode.description) || t("dashboard.pendingContent")}
                    </p>
                    <div className="episodeMeta">
                      <span>{formatDate(episode.published_at ?? episode.created_at)}</span>
                      <span>
                        <ClockIcon size={15} /> {formatDuration(episode.duration_ms)}
                      </span>
                    </div>
                  </div>
                  <span className="rowArrow">
                    <ArrowIcon size={20} />
                  </span>
                </Link>
              ))}
            </div>
            <div className="libraryPagination" aria-live="polite">
              <p>
                {t("dashboard.showingEpisodes", {
                  shown: formatNumber(episodes.length),
                  total: formatNumber(total),
                })}
              </p>
              {loadMoreError ? (
                <span className="formError">
                  {localizeError(loadMoreError, t, "errors.libraryLoadMore")}
                </span>
              ) : null}
              {hasMoreEpisodes(episodes.length, total) ? (
                <button
                  aria-disabled={loadingMore}
                  className="secondaryButton"
                  onClick={() => {
                    if (!loadingMore) void handleLoadMore();
                  }}
                  type="button"
                >
                  {loadingMore ? t("dashboard.loading") : t("dashboard.loadMore")}
                </button>
              ) : (
                <span>{t("dashboard.allLoaded")}</span>
              )}
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

function EpisodeArtwork({ episode }: { episode: EpisodeBrief }) {
  if (episode.artwork_url) {
    return <img alt="" className="episodeArtwork" loading="lazy" src={episode.artwork_url} />;
  }
  return (
    <div className="episodeArtwork artworkFallback" aria-hidden="true">
      <span>{episode.title.slice(0, 1).toUpperCase()}</span>
    </div>
  );
}

function LibrarySkeleton() {
  const { t } = useI18n();
  return (
    <div className="episodeList" aria-label={t("dashboard.loadingEpisodes")}>
      {[0, 1, 2].map((item) => (
        <div className="episodeRow skeletonRow" key={item}>
          <div className="episodeArtwork skeleton" />
          <div className="episodeCopy">
            <div className="skeleton skeletonTitle" />
            <div className="skeleton skeletonText" />
            <div className="skeleton skeletonText short" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyLibrary() {
  const { t } = useI18n();
  return (
    <div className="emptyLibrary">
      <div className="emptySymbol">
        <SparkIcon size={27} />
      </div>
      <h3>{t("dashboard.emptyTitle")}</h3>
      <p>{t("dashboard.emptyBody")}</p>
    </div>
  );
}

"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { EditIcon, SearchIcon } from "@/components/icons";
import { SpeakerDialog } from "@/components/speaker-dialog";
import { api } from "@/lib/api";
import { localizeError } from "@/lib/errors";
import { formatDuration } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useI18n } from "@/lib/i18n/provider";
import { restoreModalTriggerFocus } from "@/lib/modal-dialog";
import { mergeTranscriptPages, replaceTranscriptSpeaker } from "@/lib/transcript-pages";
import type { Segment, Transcript } from "@/lib/types";

const NO_SEGMENTS: Segment[] = [];

interface TranscriptError {
  cause: unknown;
  fallback: MessageKey;
}

export function TranscriptView({
  episodeId,
  transcript,
  onSeek,
}: {
  episodeId: string;
  transcript: Transcript | null;
  onSeek: (milliseconds: number) => void;
}) {
  const { formatNumber, t, tp } = useI18n();
  const [query, setQuery] = useState("");
  const [browseTranscript, setBrowseTranscript] = useState(transcript);
  const [searchTranscript, setSearchTranscript] = useState<Transcript | null>(null);
  const [searching, setSearching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [editingSpeaker, setEditingSpeaker] = useState<Segment["speaker"] | null>(null);
  const [speakerName, setSpeakerName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<TranscriptError | null>(null);
  const scrollElement = useRef<HTMLDivElement>(null);
  const speakerEditTrigger = useRef<HTMLButtonElement | null>(null);

  const normalizedQuery = normalizeQuery(query);
  const activeSearch = searchTranscript?.query === normalizedQuery ? searchTranscript : null;
  const activeTranscript = normalizedQuery ? activeSearch : browseTranscript;
  const segments = activeTranscript?.segments ?? NO_SEGMENTS;
  const transcriptId = transcript?.id ?? null;
  const transcriptVersion = transcript?.version ?? null;
  const latestSegments = useRef(segments);
  latestSegments.current = segments;
  const getItemKey = useCallback(
    (index: number) => segments[index]?.id ?? `segment-${index}`,
    [segments],
  );
  // TanStack Virtual intentionally exposes imperative measurement functions.
  // eslint-disable-next-line react-hooks/incompatible-library
  const rowVirtualizer = useVirtualizer({
    count: segments.length,
    estimateSize: () => 96,
    getItemKey,
    getScrollElement: () => scrollElement.current,
    overscan: 6,
  });

  useEffect(() => {
    setBrowseTranscript((current) =>
      current && transcript && hasSameContent(current, transcript) ? current : transcript,
    );
    setSearchTranscript((current) =>
      current && transcript && hasSameContent(current, transcript) ? current : null,
    );
  }, [transcript]);

  useEffect(() => {
    if (!transcriptId || transcriptVersion === null || !normalizedQuery) {
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearching(true);
      setError(null);
      void api
        .getTranscript(episodeId, {
          query: normalizedQuery,
          signal: controller.signal,
        })
        .then((next) => {
          if (!controller.signal.aborted) setSearchTranscript(next);
        })
        .catch((cause) => {
          if (!controller.signal.aborted) {
            setError({ cause, fallback: "errors.transcriptSearch" });
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false);
        });
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [episodeId, normalizedQuery, transcriptId, transcriptVersion]);

  useEffect(() => {
    rowVirtualizer.scrollToOffset(0);
    const anchorId = activeTranscript?.anchor_segment_id;
    if (!anchorId) return;
    const anchorIndex = latestSegments.current.findIndex((segment) => segment.id === anchorId);
    if (anchorIndex >= 0) rowVirtualizer.scrollToIndex(anchorIndex, { align: "center" });
  }, [
    activeTranscript?.anchor_segment_id,
    activeTranscript?.id,
    activeTranscript?.query,
    activeTranscript?.version,
    rowVirtualizer,
  ]);

  function beginSpeakerEdit(segment: Segment, trigger: HTMLButtonElement) {
    if (!segment.speaker) return;
    speakerEditTrigger.current = trigger;
    setEditingSpeaker(segment.speaker);
    setSpeakerName(segment.speaker.display_name ?? segment.speaker.label);
    setError(null);
  }

  function closeSpeakerEdit() {
    const trigger = speakerEditTrigger.current;
    setEditingSpeaker(null);
    speakerEditTrigger.current = null;
    restoreModalTriggerFocus(trigger, scrollElement.current, (callback) => {
      if (document.visibilityState === "visible") {
        window.requestAnimationFrame(callback);
        return;
      }
      const restoreWhenVisible = () => {
        if (document.visibilityState !== "visible") return;
        document.removeEventListener("visibilitychange", restoreWhenVisible);
        window.requestAnimationFrame(callback);
      };
      document.addEventListener("visibilitychange", restoreWhenVisible);
    });
  }

  async function saveSpeaker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingSpeaker || !speakerName.trim()) return;
    setSaving(true);
    try {
      const updated = await api.updateSpeaker(episodeId, editingSpeaker.id, speakerName.trim());
      setBrowseTranscript((current) => replaceTranscriptSpeaker(current, updated));
      setSearchTranscript((current) => replaceTranscriptSpeaker(current, updated));
      setError(null);
      closeSpeakerEdit();
    } catch (cause) {
      setError({ cause, fallback: "errors.speakerUpdate" });
    } finally {
      setSaving(false);
    }
  }

  async function loadMore() {
    const current = activeTranscript;
    if (!current?.next_cursor || loadingMore) return;
    setLoadingMore(true);
    setError(null);
    try {
      const next = await api.getTranscript(episodeId, {
        cursor: current.next_cursor,
        query: current.query ?? undefined,
        limit: current.limit,
      });
      if (current.query) {
        setSearchTranscript((page) => (page ? mergeTranscriptPages(page, next) : next));
      } else {
        setBrowseTranscript((page) => (page ? mergeTranscriptPages(page, next) : next));
      }
    } catch (cause) {
      setError({ cause, fallback: "errors.segmentsLoadMore" });
    } finally {
      setLoadingMore(false);
    }
  }

  function changeQuery(value: string) {
    setQuery(value);
    setError(null);
    if (!normalizeQuery(value)) setSearching(false);
  }

  if (!transcript) {
    return (
      <div className="emptyArtifact">
        <h2>{t("transcript.unavailable")}</h2>
        <p>{t("transcript.pending")}</p>
      </div>
    );
  }

  const virtualRows = rowVirtualizer.getVirtualItems();
  const localizedError = error ? localizeError(error.cause, t, error.fallback) : null;
  return (
    <div className="transcriptView">
      <div className="transcriptToolbar">
        <div>
          <span className="panelLabel">
            {t("transcript.version", { version: formatNumber(transcript.version) })}
          </span>
          <h2>{t("transcript.title")}</h2>
        </div>
        <label className="searchControl">
          <SearchIcon size={18} />
          <input
            aria-label={t("transcript.searchLabel")}
            onChange={(event) => changeQuery(event.target.value)}
            placeholder={t("transcript.searchPlaceholder")}
            value={query}
          />
        </label>
      </div>
      <div className="transcriptStats">
        <span>
          {tp("transcript.segments", transcript.segment_count, {
            count: formatNumber(transcript.segment_count),
          })}
        </span>
        <span>
          {transcript.provider}
          {transcript.model ? ` · ${transcript.model}` : ""}
        </span>
        {normalizedQuery && activeSearch ? (
          <span>
            {tp("transcript.matches", activeSearch.matched_count, {
              count: formatNumber(activeSearch.matched_count),
            })}
          </span>
        ) : (
          <span>
            {tp("transcript.loaded", segments.length, {
              count: formatNumber(segments.length),
            })}
          </span>
        )}
      </div>
      <div className="segmentList" ref={scrollElement} tabIndex={-1}>
        {segments.length > 0 ? (
          <div
            className="virtualSegmentCanvas"
            style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
          >
            {virtualRows.map((virtualRow) => {
              const segment = segments[virtualRow.index];
              const speaker =
                segment.speaker?.display_name ?? segment.speaker?.label ?? t("transcript.speaker");
              return (
                <article
                  className="segmentRow"
                  data-index={virtualRow.index}
                  key={virtualRow.key}
                  ref={rowVirtualizer.measureElement}
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                >
                  <button
                    className="timestampButton"
                    onClick={() => onSeek(segment.start_ms)}
                    type="button"
                  >
                    {formatDuration(segment.start_ms)}
                  </button>
                  <div className="segmentBody">
                    <button
                      className="speakerButton"
                      onClick={(event) => beginSpeakerEdit(segment, event.currentTarget)}
                      type="button"
                    >
                      {speaker}
                      <EditIcon size={13} />
                    </button>
                    <p>{highlight(segment.text, normalizedQuery)}</p>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="noResults">
            {searching ? t("transcript.searching") : t("transcript.noResults")}
          </p>
        )}
      </div>
      {activeTranscript?.next_cursor ? (
        <div className="transcriptPagination">
          <span>
            {t("transcript.pagination", {
              shown: formatNumber(segments.length),
              total: formatNumber(activeTranscript.matched_count),
            })}
          </span>
          <button
            className="secondaryButton"
            disabled={loadingMore}
            onClick={() => void loadMore()}
            type="button"
          >
            {loadingMore ? t("dashboard.loading") : t("dashboard.loadMore")}
          </button>
        </div>
      ) : null}
      {localizedError ? <p className="formError transcriptError">{localizedError}</p> : null}

      {editingSpeaker ? (
        <SpeakerDialog
          error={localizedError}
          onClose={closeSpeakerEdit}
          onNameChange={setSpeakerName}
          onSubmit={(event) => void saveSpeaker(event)}
          saving={saving}
          speakerName={speakerName}
        />
      ) : null}
    </div>
  );
}

function normalizeQuery(query: string) {
  return query.trim().replace(/\s+/g, " ").toLowerCase();
}

function hasSameContent(left: Transcript, right: Transcript) {
  return left.id === right.id && left.version === right.version;
}

function highlight(text: string, query: string) {
  if (!query) return text;
  const index = text.toLowerCase().indexOf(query);
  if (index < 0) return text;
  return (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, index + query.length)}</mark>
      {text.slice(index + query.length)}
    </>
  );
}

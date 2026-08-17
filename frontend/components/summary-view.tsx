"use client";

import { useState } from "react";

import { ClockIcon, SparkIcon } from "@/components/icons";
import { api } from "@/lib/api";
import { localizeError } from "@/lib/errors";
import { formatDuration } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import type { Summary } from "@/lib/types";

export function SummaryView({
  episodeId,
  summary,
  onGenerated,
  onSeek,
}: {
  episodeId: string;
  summary: Summary | null;
  onGenerated: () => Promise<void>;
  onSeek: (milliseconds: number) => void;
}) {
  const { t } = useI18n();
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<unknown | null>(null);

  async function generate(force: boolean) {
    setGenerating(true);
    setError(null);
    try {
      await api.createSummary(episodeId, force);
      await onGenerated();
    } catch (cause) {
      setError(cause);
    } finally {
      setGenerating(false);
    }
  }

  if (!summary) {
    return (
      <div className="emptyArtifact">
        <span className="emptySymbol">
          <SparkIcon size={25} />
        </span>
        <h2>{t("summary.notAvailable")}</h2>
        <p>{t("summary.requiresTranscript")}</p>
        <button
          className="primaryButton"
          disabled={generating}
          onClick={() => void generate(false)}
          type="button"
        >
          {generating ? t("summary.generating") : t("summary.generate")}
        </button>
        {error ? (
          <p className="formError">{localizeError(error, t, "errors.summaryGenerate")}</p>
        ) : null}
      </div>
    );
  }

  const content = summary.content_json;
  return (
    <div className="summaryView">
      <section className="summaryLead">
        <div className="artifactHeading">
          <div>
            <span className="panelLabel">{t("summary.executive")}</span>
            <h2>{t("summary.overview")}</h2>
          </div>
          <button
            className="textButton"
            disabled={generating}
            onClick={() => void generate(true)}
            type="button"
          >
            {generating ? t("summary.updating") : t("summary.regenerate")}
          </button>
        </div>
        <p>{content.executive_summary}</p>
        {content.topics?.length ? (
          <div className="topicList" aria-label={t("summary.topics")}>
            {content.topics.slice(0, 10).map((topic) => (
              <span key={topic}>{topic}</span>
            ))}
          </div>
        ) : null}
      </section>

      {content.key_takeaways?.length ? (
        <section className="artifactSection">
          <h2>{t("summary.takeaways")}</h2>
          <ol className="takeawayList">
            {content.key_takeaways.map((item, index) => (
              <li key={`${item.text}-${index}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>{item.text}</p>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {content.chapters?.length ? (
        <section className="artifactSection">
          <h2>{t("summary.chapters")}</h2>
          <div className="chapterList">
            {content.chapters.map((chapter, index) => (
              <button
                className="chapterRow"
                key={`${chapter.title}-${index}`}
                onClick={() => onSeek(chapter.start_ms)}
                type="button"
              >
                <span className="chapterTime">
                  <ClockIcon size={15} /> {formatDuration(chapter.start_ms)}
                </span>
                <span className="chapterCopy">
                  <strong>{chapter.title}</strong>
                  <span>{chapter.summary}</span>
                </span>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {content.detailed_summary ? (
        <section className="artifactSection detailedSummary">
          <h2>{t("summary.detailed")}</h2>
          {content.detailed_summary.split(/\n{2,}/).map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </section>
      ) : null}
      {error ? (
        <p className="formError">{localizeError(error, t, "errors.summaryGenerate")}</p>
      ) : null}
    </div>
  );
}

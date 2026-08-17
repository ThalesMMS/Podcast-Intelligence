"use client";

import { useEffect, useId, useState } from "react";

import { AlertIcon, CheckIcon, ClockIcon } from "@/components/icons";
import { StatusBadge } from "@/components/status-badge";
import { localizeErrorCode } from "@/lib/errors";
import { formatStatus } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useI18n } from "@/lib/i18n/provider";
import { getJobPanelMode } from "@/lib/job-presentation";
import type { Job } from "@/lib/types";

const labels: Record<string, MessageKey> = {
  resolve_source: "job.resolveSource",
  acquire_media: "job.acquireMedia",
  normalize_audio: "job.normalizeAudio",
  transcribe: "job.transcribe",
  index: "job.index",
  summarize: "job.summarize",
  finalize: "job.finalize",
};

export function JobPanel({ job }: { job: Job | null }) {
  const { formatNumber, t, tp } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();

  useEffect(() => {
    if (job?.error_message) {
      console.error("Job processing error", {
        code: job.error_code,
        jobId: job.id,
        message: job.error_message,
      });
    }
  }, [job?.error_code, job?.error_message, job?.id]);

  if (!job) {
    return (
      <aside className="jobPanel quietPanel">
        <h2>{t("job.title")}</h2>
        <p>{t("job.none")}</p>
      </aside>
    );
  }

  const mode = getJobPanelMode(job.status);
  const percent = Math.round(job.progress * 100);
  const localizedPercent = formatNumber(percent);
  return (
    <aside className={`jobPanel jobPanel-${mode}${expanded ? " jobPanel-expanded" : ""}`}>
      <div className="jobPanelHeader">
        <div>
          <span className="panelLabel">{t("job.pipeline")}</span>
          <h2>{t("job.title")}</h2>
        </div>
        <StatusBadge status={job.status} />
      </div>
      <div className="progressTrack" aria-label={t("job.progress", { percent: localizedPercent })}>
        <span style={{ width: `${Math.max(2, job.progress * 100)}%` }} />
      </div>
      <p className="progressCopy">{t("job.progress", { percent: localizedPercent })}</p>
      {mode === "completed" ? (
        <button
          aria-controls={detailsId}
          aria-expanded={expanded}
          className="jobPanelToggle"
          onClick={() => setExpanded((current) => !current)}
          type="button"
        >
          <span>
            {tp("job.steps", job.steps.length, { count: formatNumber(job.steps.length) })}
          </span>
          <strong>{expanded ? t("job.hideSteps") : t("job.viewSteps")}</strong>
        </button>
      ) : null}
      <div className="jobPanelDetails" id={detailsId}>
        <ol className="stepList">
          {job.steps.map((step) => (
            <li className={`stepItem step-${step.status}`} key={step.name}>
              <span className="stepIcon">
                {step.status === "completed" ? <CheckIcon size={16} /> : null}
                {step.status === "failed" ? <AlertIcon size={16} /> : null}
                {step.status !== "completed" && step.status !== "failed" ? (
                  <ClockIcon size={16} />
                ) : null}
              </span>
              <div>
                <strong>{labels[step.name] ? t(labels[step.name]) : step.name}</strong>
                <small>
                  {step.status === "running" && step.attempts > 0
                    ? t("job.attempt", { count: formatNumber(step.attempts) })
                    : formatStatus(step.status, t)}
                </small>
              </div>
            </li>
          ))}
        </ol>
        {job.error_code || job.error_message ? (
          <div className="jobError">
            <AlertIcon size={18} />
            <div>
              <strong>{localizeErrorCode(job.error_code, t, "job.pipelineFailure")}</strong>
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

import type { EpisodeStatus, Job } from "./types";

const TERMINAL_JOB_STATUSES = new Set<Job["status"]>(["completed", "failed", "cancelled"]);

function completed(job: Job | null, stepName: string): boolean {
  return Boolean(job?.steps.some((step) => step.name === stepName && step.status === "completed"));
}

export interface WorkspaceRefreshPlan {
  continuePolling: boolean;
  refreshEpisode: boolean;
  refreshTranscript: boolean;
}

export function getWorkspaceRefreshPlan(previous: Job | null, current: Job): WorkspaceRefreshPlan {
  const statusBecameTerminal =
    TERMINAL_JOB_STATUSES.has(current.status) && previous?.status !== current.status;
  const summaryChanged = completed(current, "summarize") && !completed(previous, "summarize");
  const finalizeChanged = completed(current, "finalize") && !completed(previous, "finalize");

  return {
    continuePolling: !TERMINAL_JOB_STATUSES.has(current.status),
    refreshEpisode: statusBecameTerminal || summaryChanged || finalizeChanged,
    refreshTranscript: completed(current, "transcribe") && !completed(previous, "transcribe"),
  };
}

export function episodeStatusFromJob(
  currentStatus: EpisodeStatus,
  jobStatus: Job["status"],
): EpisodeStatus {
  if (jobStatus === "queued") return "queued";
  if (["running", "retrying", "waiting_for_user"].includes(jobStatus)) return "processing";
  if (jobStatus === "completed") return "ready";
  if (jobStatus === "failed") return "failed";
  return currentStatus;
}

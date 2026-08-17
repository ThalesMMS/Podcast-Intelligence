import type { JobStatus } from "./types";

const PRIORITY_STATUSES = new Set<JobStatus>([
  "queued",
  "running",
  "retrying",
  "waiting_for_user",
  "failed",
]);

export type JobPanelMode = "completed" | "priority" | "secondary";

export function getJobPanelMode(status: JobStatus): JobPanelMode {
  if (status === "completed") return "completed";
  return PRIORITY_STATUSES.has(status) ? "priority" : "secondary";
}

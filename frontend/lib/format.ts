import type { MessageKey, Translate } from "@/lib/i18n/messages";

export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds == null || milliseconds < 0) return "—";
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
    : `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function formatStatus(value: string, t: Translate): string {
  const labels: Record<string, MessageKey> = {
    draft: "status.draft",
    queued: "status.queued",
    processing: "status.processing",
    ready: "status.ready",
    failed: "status.failed",
    running: "status.running",
    waiting_for_user: "status.waitingForUser",
    retrying: "status.retrying",
    completed: "status.completed",
    cancelled: "status.cancelled",
    pending: "status.pending",
    skipped: "status.skipped",
  };
  const key = labels[value];
  return key ? t(key) : value;
}

export function excerpt(value: string | null | undefined, length = 170): string {
  const normalized = value?.replace(/\s+/g, " ").trim() ?? "";
  return normalized.length > length ? `${normalized.slice(0, length - 1)}…` : normalized;
}

import type {
  ChatResponse,
  EpisodeDetail,
  EpisodeListResponse,
  Job,
  PlaybackAccess,
  Speaker,
  Summary,
  Transcript,
} from "@/lib/types";
import { ClientError } from "@/lib/errors";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class APIError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

interface ValidationErrorDetail {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
}

interface ErrorPayload {
  message?: string;
  detail?: string | ValidationErrorDetail[];
  code?: string;
}

function isErrorPayload(value: unknown): value is ErrorPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatValidationDetail(detail: ErrorPayload["detail"]): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;

  const messages = detail.flatMap((error) => {
    if (!error || typeof error !== "object" || typeof error.msg !== "string") return [];
    const location = Array.isArray(error.loc)
      ? error.loc
          .filter((part) => part !== "body")
          .map(String)
          .join(".")
      : "";
    return [location ? `${location}: ${error.msg}` : error.msg];
  });
  return messages.length > 0 ? messages.join("; ") : null;
}

function mediaContentType(file: File): string {
  const contentType = file.type.trim().toLowerCase();
  if (!/^(?:audio|video)\/[a-z0-9][a-z0-9!#$&^_.+-]*$/.test(contentType)) {
    throw new ClientError("unsupported_media_type");
  }
  return contentType;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const hasJsonBody = typeof init?.body === "string";
  if (hasJsonBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: init?.headers !== undefined || hasJsonBody ? headers : undefined,
    cache: "no-store",
  });
  if (!response.ok) {
    const rawPayload: unknown = await response.json().catch(() => null);
    const payload = isErrorPayload(rawPayload) ? rawPayload : null;
    const message =
      (typeof payload?.message === "string" ? payload.message : null) ??
      formatValidationDetail(payload?.detail) ??
      `HTTP request failed with status ${response.status}`;
    throw new APIError(
      message,
      response.status,
      typeof payload?.code === "string" ? payload.code : undefined,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  listEpisodes: (options: { limit?: number; offset?: number; signal?: AbortSignal } = {}) => {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    const queryString = params.toString();
    const query = queryString ? `?${queryString}` : "";
    return request<EpisodeListResponse>(`/v1/episodes${query}`, {
      signal: options.signal,
    });
  },
  getEpisode: (id: string, options: { signal?: AbortSignal } = {}) =>
    request<EpisodeDetail>(`/v1/episodes/${id}`, { signal: options.signal }),
  getPlayback: (id: string, options: { signal?: AbortSignal } = {}) =>
    request<PlaybackAccess>(`/v1/episodes/${id}/playback`, {
      signal: options.signal,
    }),
  getJob: (id: string, options: { signal?: AbortSignal } = {}) =>
    request<Job>(`/v1/jobs/${id}`, { signal: options.signal }),
  getTranscript: (
    id: string,
    options: {
      cursor?: string;
      query?: string;
      atMs?: number;
      limit?: number;
      signal?: AbortSignal;
    } = {},
  ) => {
    const params = new URLSearchParams();
    if (options.cursor) params.set("cursor", options.cursor);
    if (options.query) params.set("q", options.query);
    if (options.atMs !== undefined) params.set("at_ms", String(options.atMs));
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    const query = params.size > 0 ? `?${params}` : "";
    return request<Transcript>(`/v1/episodes/${id}/transcript${query}`, {
      signal: options.signal,
    });
  },
  listSummaries: (id: string) => request<Summary[]>(`/v1/episodes/${id}/summaries`),
  createSummary: (id: string, force = false) =>
    request<{ summary: Summary["content_json"]; summary_id: string }>(
      `/v1/episodes/${id}/summaries`,
      { method: "POST", body: JSON.stringify({ force }) },
    ),
  updateSpeaker: (episodeId: string, speakerId: string, displayName: string) =>
    request<Speaker>(`/v1/episodes/${episodeId}/speakers/${speakerId}`, {
      method: "PATCH",
      body: JSON.stringify({ display_name: displayName, confirmed_by_user: true }),
    }),
  createConversation: (episodeId: string) =>
    request<{ id: string }>("/v1/conversations", {
      method: "POST",
      body: JSON.stringify({ episode_id: episodeId }),
    }),
  ask: (conversationId: string, question: string) =>
    request<ChatResponse>(`/v1/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  initiateUpload: (file: File) => {
    const contentType = mediaContentType(file);
    return request<{
      object_key: string;
      upload_url: string;
      method: "POST";
      fields: Record<string, string>;
    }>("/v1/uploads", {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        content_type: contentType,
        size_bytes: file.size,
      }),
    });
  },
  uploadObject: async (url: string, fields: Record<string, string>, file: File) => {
    const form = new FormData();
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    form.append("file", file);
    const response = await fetch(url, { method: "POST", body: form });
    if (!response.ok) throw new APIError("File upload failed", response.status, "upload_failed");
  },
  createUploadImport: (objectKey: string, file: File, language?: string) => {
    const contentType = mediaContentType(file);
    return request<{ episode_id: string; job_id: string }>("/v1/imports", {
      method: "POST",
      body: JSON.stringify({
        source: {
          type: "upload",
          object_key: objectKey,
          filename: file.name,
          content_type: contentType,
        },
        options: { language: language || null, diarization: false, generate_summary: true },
      }),
    });
  },
  createUrlImport: (
    sourceType: "direct_url" | "rss" | "apple" | "spotify",
    url: string,
    episodeTitle?: string,
    language?: string,
    rssUrlHint?: string,
  ) =>
    request<{ episode_id: string; job_id: string }>("/v1/imports", {
      method: "POST",
      body: JSON.stringify({
        source: {
          type: sourceType,
          url,
          episode_title: episodeTitle || null,
          rss_url_hint:
            sourceType === "spotify" || sourceType === "apple" ? rssUrlHint || null : null,
        },
        options: { language: language || null, diarization: false, generate_summary: true },
      }),
    }),
};

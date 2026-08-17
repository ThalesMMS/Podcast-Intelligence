export type EpisodeStatus = "draft" | "queued" | "processing" | "ready" | "failed";
export type JobStatus =
  "queued" | "running" | "waiting_for_user" | "retrying" | "completed" | "failed" | "cancelled";

export interface ShowBrief {
  id: string;
  title: string;
  author: string | null;
  artwork_url: string | null;
}

export interface Step {
  name: string;
  ordinal: number;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  attempts: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  metrics_json: Record<string, unknown>;
}

export interface Job {
  id: string;
  episode_id: string;
  status: JobStatus;
  current_step: string | null;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  steps: Step[];
}

export interface SummaryContent {
  executive_summary: string;
  detailed_summary: string;
  chapters: Array<{
    title: string;
    summary: string;
    start_ms: number;
    end_ms: number;
    supporting_segment_ids: string[];
  }>;
  key_takeaways: Array<{ text: string; supporting_segment_ids: string[] }>;
  people: string[];
  organizations: string[];
  topics: string[];
  open_questions: Array<{ text: string; supporting_segment_ids: string[] }>;
}

export interface Summary {
  id: string;
  kind: string;
  version: number;
  provider: string;
  model: string | null;
  content_json: SummaryContent;
  created_at: string;
}

export interface Speaker {
  id: string;
  label: string;
  display_name: string | null;
  confidence: number | null;
  attribution_method: string | null;
  confirmed_by_user: boolean;
}

export interface EpisodeBrief {
  id: string;
  title: string;
  description: string | null;
  canonical_url: string | null;
  artwork_url: string | null;
  published_at: string | null;
  duration_ms: number | null;
  language: string | null;
  status: EpisodeStatus;
  show: ShowBrief | null;
  created_at: string;
}

export interface EpisodeDetail extends EpisodeBrief {
  speakers: Speaker[];
  summaries: Summary[];
  playback_url: string | null;
  playback_expires_at: string | null;
  latest_job: Job | null;
}

export interface PlaybackAccess {
  playback_url: string;
  expires_at: string;
  expires_in: number;
}

export interface Segment {
  id: string;
  ordinal: number;
  start_ms: number;
  end_ms: number;
  text: string;
  confidence: number | null;
  language: string | null;
  speaker: Speaker | null;
}

export interface Transcript {
  id: string;
  version: number;
  provider: string;
  model: string | null;
  language: string | null;
  segment_count: number;
  matched_count: number;
  limit: number;
  query: string | null;
  next_cursor: string | null;
  anchor_segment_id: string | null;
  segments: Segment[];
}

export interface Citation {
  segment_id: string;
  start_ms: number;
  end_ms: number;
  speaker: string | null;
  quote: string;
}

export interface ChatResponse {
  message_id: string;
  answer: string;
  citations: Citation[];
  insufficient_evidence: boolean;
}

export interface EpisodeListResponse {
  items: EpisodeBrief[];
  total: number;
  active_count: number;
  limit: number;
  offset: number;
}

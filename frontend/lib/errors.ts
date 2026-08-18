import type { MessageKey, Translate } from "@/lib/i18n/messages";

export type ClientErrorCode =
  | "media_required"
  | "source_url_required"
  | "unsupported_media_type"
  | "upload_failed"
  | "playback_replacement_failed";

type ErrorMessageKey = Extract<MessageKey, `errors.${string}`>;

const ERROR_CODE_KEYS: Record<string, ErrorMessageKey> = {
  application_error: "errors.generic",
  conflict: "errors.conflict",
  job_cancelled: "errors.jobCancelled",
  media_required: "errors.selectMedia",
  media_validation_failed: "errors.mediaValidation",
  not_found: "errors.notFound",
  playback_replacement_failed: "errors.playbackRenewal",
  provider_configuration_error: "errors.providerConfiguration",
  provider_execution_error: "errors.providerExecution",
  source_resolution_failed: "errors.sourceResolution",
  source_url_required: "errors.sourceUrl",
  unsafe_remote_url: "errors.unsafeRemoteUrl",
  unsupported_media_type: "errors.unsupportedMedia",
  upload_failed: "errors.upload",
};

const HTTP_STATUS_KEYS: Record<number, ErrorMessageKey> = {
  400: "errors.badRequest",
  404: "errors.notFound",
  409: "errors.conflict",
  422: "errors.validation",
};

interface ErrorMetadata {
  code?: unknown;
  status?: unknown;
}

export interface JobErrorPresentation {
  title: string;
  message: string;
  action?: string;
  technicalDetails?: string;
}

export class ClientError extends Error {
  constructor(readonly code: ClientErrorCode) {
    super(code);
    this.name = "ClientError";
  }
}

function metadata(error: unknown): ErrorMetadata | null {
  return typeof error === "object" && error !== null ? (error as ErrorMetadata) : null;
}

export function localizeErrorCode(
  code: string | null | undefined,
  t: Translate,
  fallback: MessageKey,
) {
  const key = code ? ERROR_CODE_KEYS[code] : undefined;
  return t(key ?? fallback);
}

export function presentJobError(
  code: string | null | undefined,
  message: string | null | undefined,
  currentStep: string | null | undefined,
  t: Translate,
): JobErrorPresentation {
  const technicalDetails = message?.trim() || undefined;
  const normalized = technicalDetails?.toLowerCase() || "";

  if (
    currentStep === "index" &&
    normalized.includes("does not support matryoshka embeddings") &&
    normalized.includes("dimensions must be unset")
  ) {
    return {
      title: "Embedding request rejected",
      message: "This embedding model uses a fixed output size and does not accept dimensions.",
      action:
        "Turn off “Send the dimensions parameter to the embedding endpoint” in Settings, then retry the job.",
      technicalDetails,
    };
  }

  if (
    currentStep === "summarize" &&
    normalized.includes("invalid json") &&
    (normalized.includes("type=json_invalid") || normalized.includes("input_value='{{"))
  ) {
    return {
      title: "Structured summary output was invalid",
      message: "The provider returned malformed JSON through the Responses API.",
      action:
        "Select Chat Completions under Structured-output API in Settings, then generate the summary again.",
      technicalDetails,
    };
  }

  return {
    title: localizeErrorCode(code, t, "job.pipelineFailure"),
    message: technicalDetails || "The job stopped before processing could finish.",
  };
}

export function localizeError(error: unknown, t: Translate, fallback: MessageKey) {
  const details = metadata(error);
  if (typeof details?.code === "string" && ERROR_CODE_KEYS[details.code]) {
    return t(ERROR_CODE_KEYS[details.code]);
  }
  if (typeof details?.status === "number" && HTTP_STATUS_KEYS[details.status]) {
    return t(HTTP_STATUS_KEYS[details.status]);
  }
  console.error("Unhandled interface error", error);
  return t(fallback);
}

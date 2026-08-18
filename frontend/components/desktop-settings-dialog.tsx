"use client";

import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { activateModalDialog, handleModalCancel } from "@/lib/modal-dialog";
import { useI18n } from "@/lib/i18n/provider";
import {
  type RuntimeConfig,
  getDesktopSettings,
  loadRuntimeConfig,
  restartDesktopEngine,
  saveDesktopSettings,
} from "@/lib/runtime";

interface DesktopSettingsForm {
  ai_profile: "demo" | "openai" | "custom";
  transcription_provider: "demo" | "openai" | "streaming_ws";
  embedding_provider: "demo" | "openai";
  llm_provider: "demo" | "openai" | "codex_cli";
  openai_api_key: string;
  openai_base_url: string;
  openai_transcription_base_url: string;
  openai_embedding_base_url: string;
  openai_llm_base_url: string;
  openai_transcription_api_key: string;
  openai_embedding_api_key: string;
  openai_llm_api_key: string;
  openai_transcription_model: string;
  openai_embedding_model: string;
  openai_llm_model: string;
  openai_llm_api: "responses" | "chat_completions";
  openai_reasoning_effort: "none" | "low" | "medium" | "high" | "xhigh" | "max";
  openai_embedding_send_dimensions: boolean;
  embedding_dimension: number;
  embedding_batch_size: number;
  streaming_stt_url: string;
  streaming_stt_api_key: string;
  streaming_stt_model: string;
  streaming_stt_language: string;
  spotify_client_id: string;
  spotify_client_secret: string;
  codex_binary: string;
  codex_model: string;
  desktop_job_workers: number;
  max_remote_file_bytes: number;
  max_audio_duration_seconds: number;
  retrieval_top_k: number;
  retrieval_lexical_weight: number;
  retrieval_vector_weight: number;
}

const DEFAULT_SETTINGS: DesktopSettingsForm = {
  ai_profile: "demo",
  transcription_provider: "demo",
  embedding_provider: "demo",
  llm_provider: "demo",
  openai_api_key: "",
  openai_base_url: "",
  openai_transcription_base_url: "",
  openai_embedding_base_url: "",
  openai_llm_base_url: "",
  openai_transcription_api_key: "",
  openai_embedding_api_key: "",
  openai_llm_api_key: "",
  openai_transcription_model: "gpt-4o-transcribe-diarize",
  openai_embedding_model: "text-embedding-3-small",
  openai_llm_model: "gpt-5.6-luna",
  openai_llm_api: "chat_completions",
  openai_reasoning_effort: "none",
  openai_embedding_send_dimensions: false,
  embedding_dimension: 1536,
  embedding_batch_size: 4,
  streaming_stt_url: "",
  streaming_stt_api_key: "",
  streaming_stt_model: "default",
  streaming_stt_language: "pt",
  spotify_client_id: "",
  spotify_client_secret: "",
  codex_binary: "codex",
  codex_model: "",
  desktop_job_workers: 2,
  max_remote_file_bytes: 1024 * 1024 * 1024,
  max_audio_duration_seconds: 6 * 60 * 60,
  retrieval_top_k: 10,
  retrieval_lexical_weight: 0.35,
  retrieval_vector_weight: 0.65,
};

function asString(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBoolean(value: unknown, fallback: boolean) {
  return typeof value === "boolean" ? value : fallback;
}

function usesUrlProtocol(value: string, protocols: readonly string[]) {
  const normalized = value.trim().toLowerCase();
  return protocols.some((protocol) => normalized.startsWith(`${protocol}://`));
}

function migrateWebSocketTranscription(settings: DesktopSettingsForm): DesktopSettingsForm {
  const transcriptionUrl = settings.openai_transcription_base_url.trim();
  if (!usesUrlProtocol(transcriptionUrl, ["ws", "wss"])) return settings;

  const openAIProfile = settings.ai_profile === "openai";
  return {
    ...settings,
    ai_profile: "custom",
    transcription_provider: "streaming_ws",
    embedding_provider: openAIProfile ? "openai" : settings.embedding_provider,
    llm_provider: openAIProfile ? "openai" : settings.llm_provider,
    streaming_stt_url: settings.streaming_stt_url || transcriptionUrl,
    streaming_stt_api_key:
      settings.streaming_stt_api_key ||
      settings.openai_transcription_api_key ||
      settings.openai_api_key,
    streaming_stt_model:
      settings.streaming_stt_model && settings.streaming_stt_model !== "default"
        ? settings.streaming_stt_model
        : settings.openai_transcription_model,
    openai_transcription_base_url: "",
    openai_transcription_api_key: "",
  };
}

function normalizeSettings(raw: Record<string, unknown>): DesktopSettingsForm {
  const value = (key: keyof DesktopSettingsForm) => raw[key] ?? raw[key.toUpperCase()];
  const normalized: DesktopSettingsForm = {
    ai_profile: asString(
      value("ai_profile"),
      DEFAULT_SETTINGS.ai_profile,
    ) as DesktopSettingsForm["ai_profile"],
    transcription_provider: asString(
      value("transcription_provider"),
      DEFAULT_SETTINGS.transcription_provider,
    ) as DesktopSettingsForm["transcription_provider"],
    embedding_provider: asString(
      value("embedding_provider"),
      DEFAULT_SETTINGS.embedding_provider,
    ) as DesktopSettingsForm["embedding_provider"],
    llm_provider: asString(
      value("llm_provider"),
      DEFAULT_SETTINGS.llm_provider,
    ) as DesktopSettingsForm["llm_provider"],
    openai_api_key: asString(value("openai_api_key"), ""),
    openai_base_url: asString(value("openai_base_url"), ""),
    openai_transcription_base_url: asString(value("openai_transcription_base_url"), ""),
    openai_embedding_base_url: asString(value("openai_embedding_base_url"), ""),
    openai_llm_base_url: asString(value("openai_llm_base_url"), ""),
    openai_transcription_api_key: asString(value("openai_transcription_api_key"), ""),
    openai_embedding_api_key: asString(value("openai_embedding_api_key"), ""),
    openai_llm_api_key: asString(value("openai_llm_api_key"), ""),
    openai_transcription_model: asString(
      value("openai_transcription_model"),
      DEFAULT_SETTINGS.openai_transcription_model,
    ),
    openai_embedding_model: asString(
      value("openai_embedding_model"),
      DEFAULT_SETTINGS.openai_embedding_model,
    ),
    openai_llm_model: asString(value("openai_llm_model"), DEFAULT_SETTINGS.openai_llm_model),
    openai_llm_api: asString(
      value("openai_llm_api"),
      DEFAULT_SETTINGS.openai_llm_api,
    ) as DesktopSettingsForm["openai_llm_api"],
    openai_reasoning_effort: asString(
      value("openai_reasoning_effort"),
      DEFAULT_SETTINGS.openai_reasoning_effort,
    ) as DesktopSettingsForm["openai_reasoning_effort"],
    openai_embedding_send_dimensions: asBoolean(
      value("openai_embedding_send_dimensions"),
      DEFAULT_SETTINGS.openai_embedding_send_dimensions,
    ),
    embedding_dimension: asNumber(
      value("embedding_dimension"),
      DEFAULT_SETTINGS.embedding_dimension,
    ),
    embedding_batch_size: asNumber(
      value("embedding_batch_size"),
      DEFAULT_SETTINGS.embedding_batch_size,
    ),
    streaming_stt_url: asString(value("streaming_stt_url"), ""),
    streaming_stt_api_key: asString(value("streaming_stt_api_key"), ""),
    streaming_stt_model: asString(
      value("streaming_stt_model"),
      DEFAULT_SETTINGS.streaming_stt_model,
    ),
    streaming_stt_language: asString(
      value("streaming_stt_language"),
      DEFAULT_SETTINGS.streaming_stt_language,
    ),
    spotify_client_id: asString(value("spotify_client_id"), ""),
    spotify_client_secret: asString(value("spotify_client_secret"), ""),
    codex_binary: asString(value("codex_binary"), DEFAULT_SETTINGS.codex_binary),
    codex_model: asString(value("codex_model"), ""),
    desktop_job_workers: asNumber(
      value("desktop_job_workers"),
      DEFAULT_SETTINGS.desktop_job_workers,
    ),
    max_remote_file_bytes: asNumber(
      value("max_remote_file_bytes"),
      DEFAULT_SETTINGS.max_remote_file_bytes,
    ),
    max_audio_duration_seconds: asNumber(
      value("max_audio_duration_seconds"),
      DEFAULT_SETTINGS.max_audio_duration_seconds,
    ),
    retrieval_top_k: asNumber(value("retrieval_top_k"), DEFAULT_SETTINGS.retrieval_top_k),
    retrieval_lexical_weight: asNumber(
      value("retrieval_lexical_weight"),
      DEFAULT_SETTINGS.retrieval_lexical_weight,
    ),
    retrieval_vector_weight: asNumber(
      value("retrieval_vector_weight"),
      DEFAULT_SETTINGS.retrieval_vector_weight,
    ),
  };
  return migrateWebSocketTranscription(normalized);
}

function compactSettings(settings: DesktopSettingsForm): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(settings).filter(([, value]) => value !== "" && value !== null),
  );
}

export function DesktopSettingsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [settings, setSettings] = useState<DesktopSettingsForm>(DEFAULT_SETTINGS);
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    const target = closeRef.current;
    if (!dialog || !target) return;
    return activateModalDialog(dialog, target);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([getDesktopSettings(), loadRuntimeConfig()])
      .then(([value, runtime]) => {
        if (!cancelled) {
          setSettings(normalizeSettings(value));
          setRuntimeInfo(runtime);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const usesCustomProviders = settings.ai_profile === "custom";
  const usesOpenAITranscription =
    settings.ai_profile === "openai" || settings.transcription_provider === "openai";
  const usesOpenAIEmbedding =
    settings.ai_profile === "openai" || settings.embedding_provider === "openai";
  const usesOpenAILLM = settings.ai_profile === "openai" || settings.llm_provider === "openai";
  const usesOpenAI = usesOpenAITranscription || usesOpenAIEmbedding || usesOpenAILLM;
  const usesStreaming = settings.transcription_provider === "streaming_ws";
  const usesCodex = settings.llm_provider === "codex_cli";
  const effectiveWeights = useMemo(
    () => settings.retrieval_lexical_weight + settings.retrieval_vector_weight,
    [settings.retrieval_lexical_weight, settings.retrieval_vector_weight],
  );

  function update<K extends keyof DesktopSettingsForm>(key: K, value: DesktopSettingsForm[K]) {
    setError(null);
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function updateProfile(profile: DesktopSettingsForm["ai_profile"]) {
    setError(null);
    setSettings((current) => ({
      ...current,
      ai_profile: profile,
      ...(profile === "demo"
        ? {
            transcription_provider: "demo" as const,
            embedding_provider: "demo" as const,
            llm_provider: "demo" as const,
          }
        : profile === "openai"
          ? {
              transcription_provider: "openai" as const,
              embedding_provider: "openai" as const,
              llm_provider: "openai" as const,
            }
          : {}),
    }));
  }

  function updateNumber<K extends keyof DesktopSettingsForm>(
    key: K,
    value: number,
    fallback: DesktopSettingsForm[K],
  ) {
    update(key, (Number.isFinite(value) ? value : fallback) as DesktopSettingsForm[K]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const httpBaseUrls = [
      settings.openai_base_url,
      usesOpenAITranscription ? settings.openai_transcription_base_url : "",
      usesOpenAIEmbedding ? settings.openai_embedding_base_url : "",
      usesOpenAILLM ? settings.openai_llm_base_url : "",
    ];
    if (httpBaseUrls.some((value) => value.trim() && !usesUrlProtocol(value, ["http", "https"]))) {
      setError(t("settings.httpUrlError"));
      return;
    }
    if (
      usesStreaming &&
      (!settings.streaming_stt_url.trim() ||
        !usesUrlProtocol(settings.streaming_stt_url, ["ws", "wss"]))
    ) {
      setError(t("settings.websocketUrlError"));
      return;
    }
    if (Math.abs(effectiveWeights - 1) > 0.001) {
      setError(t("settings.weightsError"));
      return;
    }
    setSaving(true);
    try {
      await saveDesktopSettings(compactSettings(settings));
      await restartDesktopEngine();
      onClose();
      window.setTimeout(() => window.location.reload(), 250);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setSaving(false);
    }
  }

  return (
    <dialog
      aria-describedby="desktop-settings-description"
      aria-labelledby="desktop-settings-title"
      aria-modal="true"
      className="desktopSettingsDialog"
      onCancel={(event) => handleModalCancel(event, onClose)}
      ref={dialogRef}
      role="dialog"
    >
      <form onSubmit={submit}>
        <header className="settingsHeader">
          <div>
            <span className="panelLabel">{t("settings.eyebrow")}</span>
            <h2 id="desktop-settings-title">{t("settings.title")}</h2>
            <p id="desktop-settings-description">{t("settings.description")}</p>
          </div>
          <button
            aria-label={t("settings.close")}
            className="dialogClose"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            ×
          </button>
        </header>

        {loading ? <div className="settingsLoading">{t("settings.loading")}</div> : null}
        {!loading ? (
          <div className="settingsBody">
            <section className="settingsSection">
              <div className="settingsSectionHeading">
                <h3>{t("settings.profileSection")}</h3>
                <p>{t("settings.profileHint")}</p>
              </div>
              <div className="settingsGrid">
                <label className="field" htmlFor="settings-profile">
                  <span>{t("settings.aiProfile")}</span>
                  <select
                    id="settings-profile"
                    onChange={(event) =>
                      updateProfile(event.target.value as DesktopSettingsForm["ai_profile"])
                    }
                    value={settings.ai_profile}
                  >
                    <option value="demo">{t("settings.profileDemo")}</option>
                    <option value="openai">{t("settings.profileOpenAI")}</option>
                    <option value="custom">{t("settings.profileCustom")}</option>
                  </select>
                </label>
                <label className="field" htmlFor="settings-workers">
                  <span>{t("settings.workers")}</span>
                  <input
                    id="settings-workers"
                    max={8}
                    min={1}
                    onChange={(event) =>
                      updateNumber("desktop_job_workers", event.target.valueAsNumber, 2)
                    }
                    type="number"
                    value={settings.desktop_job_workers}
                  />
                </label>
              </div>
              {usesCustomProviders ? (
                <div className="settingsGrid threeColumns">
                  <label className="field" htmlFor="settings-transcription-provider">
                    <span>{t("settings.transcriptionProvider")}</span>
                    <select
                      id="settings-transcription-provider"
                      onChange={(event) =>
                        update(
                          "transcription_provider",
                          event.target.value as DesktopSettingsForm["transcription_provider"],
                        )
                      }
                      value={settings.transcription_provider}
                    >
                      <option value="demo">Demo</option>
                      <option value="openai">{t("settings.providerOpenAIHttp")}</option>
                      <option value="streaming_ws">WebSocket STT</option>
                    </select>
                  </label>
                  <label className="field" htmlFor="settings-embedding-provider">
                    <span>{t("settings.embeddingProvider")}</span>
                    <select
                      id="settings-embedding-provider"
                      onChange={(event) =>
                        update(
                          "embedding_provider",
                          event.target.value as DesktopSettingsForm["embedding_provider"],
                        )
                      }
                      value={settings.embedding_provider}
                    >
                      <option value="demo">Demo</option>
                      <option value="openai">{t("settings.providerOpenAIHttp")}</option>
                    </select>
                  </label>
                  <label className="field" htmlFor="settings-llm-provider">
                    <span>{t("settings.llmProvider")}</span>
                    <select
                      id="settings-llm-provider"
                      onChange={(event) =>
                        update(
                          "llm_provider",
                          event.target.value as DesktopSettingsForm["llm_provider"],
                        )
                      }
                      value={settings.llm_provider}
                    >
                      <option value="demo">Demo</option>
                      <option value="openai">{t("settings.providerOpenAIHttp")}</option>
                      <option value="codex_cli">Codex CLI</option>
                    </select>
                  </label>
                </div>
              ) : null}
            </section>

            {usesOpenAI ? (
              <section className="settingsSection">
                <div className="settingsSectionHeading">
                  <h3>{t("settings.openAISection")}</h3>
                  <p>{t("settings.openAIHint")}</p>
                </div>
                <div className="settingsGrid">
                  <label className="field" htmlFor="settings-openai-url">
                    <span>{t("settings.sharedBaseUrl")}</span>
                    <input
                      id="settings-openai-url"
                      onChange={(event) => update("openai_base_url", event.target.value)}
                      placeholder="https://api.openai.com/v1"
                      type="url"
                      value={settings.openai_base_url}
                    />
                  </label>
                  <label className="field" htmlFor="settings-openai-key">
                    <span>{t("settings.sharedApiKey")}</span>
                    <input
                      autoComplete="off"
                      id="settings-openai-key"
                      onChange={(event) => update("openai_api_key", event.target.value)}
                      placeholder="sk-…"
                      type="password"
                      value={settings.openai_api_key}
                    />
                  </label>
                </div>
                <div className="settingsGrid threeColumns">
                  {usesOpenAITranscription ? (
                    <label className="field" htmlFor="settings-transcription-model">
                      <span>{t("settings.transcriptionModel")}</span>
                      <input
                        id="settings-transcription-model"
                        onChange={(event) =>
                          update("openai_transcription_model", event.target.value)
                        }
                        value={settings.openai_transcription_model}
                      />
                    </label>
                  ) : null}
                  {usesOpenAIEmbedding ? (
                    <label className="field" htmlFor="settings-embedding-model">
                      <span>{t("settings.embeddingModel")}</span>
                      <input
                        id="settings-embedding-model"
                        onChange={(event) => update("openai_embedding_model", event.target.value)}
                        value={settings.openai_embedding_model}
                      />
                    </label>
                  ) : null}
                  {usesOpenAILLM ? (
                    <label className="field" htmlFor="settings-llm-model">
                      <span>{t("settings.llmModel")}</span>
                      <input
                        id="settings-llm-model"
                        onChange={(event) => update("openai_llm_model", event.target.value)}
                        value={settings.openai_llm_model}
                      />
                    </label>
                  ) : null}
                </div>
                <div className="settingsGrid threeColumns">
                  {usesOpenAILLM ? (
                    <>
                      <label className="field" htmlFor="settings-llm-api">
                        <span>{t("settings.llmApi")}</span>
                        <select
                          id="settings-llm-api"
                          onChange={(event) =>
                            update(
                              "openai_llm_api",
                              event.target.value as DesktopSettingsForm["openai_llm_api"],
                            )
                          }
                          value={settings.openai_llm_api}
                        >
                          <option value="responses">Responses</option>
                          <option value="chat_completions">Chat Completions</option>
                        </select>
                      </label>
                      <label className="field" htmlFor="settings-reasoning">
                        <span>{t("settings.reasoningEffort")}</span>
                        <select
                          id="settings-reasoning"
                          onChange={(event) =>
                            update(
                              "openai_reasoning_effort",
                              event.target.value as DesktopSettingsForm["openai_reasoning_effort"],
                            )
                          }
                          value={settings.openai_reasoning_effort}
                        >
                          {(["none", "low", "medium", "high", "xhigh", "max"] as const).map(
                            (level) => (
                              <option key={level} value={level}>
                                {level}
                              </option>
                            ),
                          )}
                        </select>
                      </label>
                    </>
                  ) : null}
                  {usesOpenAIEmbedding ? (
                    <label className="field" htmlFor="settings-embedding-dimension">
                      <span>{t("settings.embeddingDimension")}</span>
                      <input
                        id="settings-embedding-dimension"
                        max={16000}
                        min={1}
                        onChange={(event) =>
                          updateNumber("embedding_dimension", event.target.valueAsNumber, 1536)
                        }
                        type="number"
                        value={settings.embedding_dimension}
                      />
                    </label>
                  ) : null}
                </div>
                {usesOpenAIEmbedding ? (
                  <label className="settingsCheckbox" htmlFor="settings-send-dimensions">
                    <input
                      checked={settings.openai_embedding_send_dimensions}
                      id="settings-send-dimensions"
                      onChange={(event) =>
                        update("openai_embedding_send_dimensions", event.target.checked)
                      }
                      type="checkbox"
                    />
                    <span>{t("settings.sendDimensions")}</span>
                  </label>
                ) : null}
                <div className="providerEndpointSettings">
                  <h4>{t("settings.providerEndpoints")}</h4>
                  {usesOpenAITranscription ? (
                    <div className="settingsGrid">
                      <label className="field" htmlFor="settings-transcription-url">
                        <span>{t("settings.transcriptionBaseUrl")}</span>
                        <input
                          id="settings-transcription-url"
                          onChange={(event) =>
                            update("openai_transcription_base_url", event.target.value)
                          }
                          placeholder={settings.openai_base_url || "https://api.openai.com/v1"}
                          type="url"
                          value={settings.openai_transcription_base_url}
                        />
                      </label>
                      <label className="field" htmlFor="settings-transcription-key">
                        <span>{t("settings.transcriptionApiKey")}</span>
                        <input
                          autoComplete="off"
                          id="settings-transcription-key"
                          onChange={(event) =>
                            update("openai_transcription_api_key", event.target.value)
                          }
                          type="password"
                          value={settings.openai_transcription_api_key}
                        />
                      </label>
                    </div>
                  ) : null}
                  {usesOpenAIEmbedding ? (
                    <div className="settingsGrid">
                      <label className="field" htmlFor="settings-embedding-url">
                        <span>{t("settings.embeddingBaseUrl")}</span>
                        <input
                          id="settings-embedding-url"
                          onChange={(event) =>
                            update("openai_embedding_base_url", event.target.value)
                          }
                          placeholder={settings.openai_base_url || "https://api.openai.com/v1"}
                          type="url"
                          value={settings.openai_embedding_base_url}
                        />
                      </label>
                      <label className="field" htmlFor="settings-embedding-key">
                        <span>{t("settings.embeddingApiKey")}</span>
                        <input
                          autoComplete="off"
                          id="settings-embedding-key"
                          onChange={(event) =>
                            update("openai_embedding_api_key", event.target.value)
                          }
                          type="password"
                          value={settings.openai_embedding_api_key}
                        />
                      </label>
                    </div>
                  ) : null}
                  {usesOpenAILLM ? (
                    <div className="settingsGrid">
                      <label className="field" htmlFor="settings-llm-url">
                        <span>{t("settings.llmBaseUrl")}</span>
                        <input
                          id="settings-llm-url"
                          onChange={(event) => update("openai_llm_base_url", event.target.value)}
                          placeholder={settings.openai_base_url || "https://api.openai.com/v1"}
                          type="url"
                          value={settings.openai_llm_base_url}
                        />
                      </label>
                      <label className="field" htmlFor="settings-llm-key">
                        <span>{t("settings.llmApiKey")}</span>
                        <input
                          autoComplete="off"
                          id="settings-llm-key"
                          onChange={(event) => update("openai_llm_api_key", event.target.value)}
                          type="password"
                          value={settings.openai_llm_api_key}
                        />
                      </label>
                    </div>
                  ) : null}
                </div>
              </section>
            ) : null}

            {usesStreaming ? (
              <section className="settingsSection">
                <div className="settingsSectionHeading">
                  <h3>{t("settings.streamingSection")}</h3>
                  <p>{t("settings.streamingHint")}</p>
                </div>
                <div className="settingsGrid">
                  <label className="field" htmlFor="settings-streaming-url">
                    <span>{t("settings.streamingUrl")}</span>
                    <input
                      id="settings-streaming-url"
                      onChange={(event) => update("streaming_stt_url", event.target.value)}
                      placeholder="wss://gateway.example/v1/transcribe"
                      type="url"
                      value={settings.streaming_stt_url}
                    />
                  </label>
                  <label className="field" htmlFor="settings-streaming-key">
                    <span>{t("settings.streamingApiKey")}</span>
                    <input
                      autoComplete="off"
                      id="settings-streaming-key"
                      onChange={(event) => update("streaming_stt_api_key", event.target.value)}
                      type="password"
                      value={settings.streaming_stt_api_key}
                    />
                  </label>
                </div>
                <div className="settingsGrid">
                  <label className="field" htmlFor="settings-streaming-model">
                    <span>{t("settings.streamingModel")}</span>
                    <input
                      id="settings-streaming-model"
                      onChange={(event) => update("streaming_stt_model", event.target.value)}
                      value={settings.streaming_stt_model}
                    />
                  </label>
                  <label className="field" htmlFor="settings-streaming-language">
                    <span>{t("settings.streamingLanguage")}</span>
                    <input
                      id="settings-streaming-language"
                      onChange={(event) => update("streaming_stt_language", event.target.value)}
                      value={settings.streaming_stt_language}
                    />
                  </label>
                </div>
              </section>
            ) : null}

            {usesCodex ? (
              <section className="settingsSection">
                <div className="settingsSectionHeading">
                  <h3>{t("settings.codexSection")}</h3>
                  <p>{t("settings.codexHint")}</p>
                </div>
                <div className="settingsGrid">
                  <label className="field" htmlFor="settings-codex-binary">
                    <span>{t("settings.codexBinary")}</span>
                    <input
                      id="settings-codex-binary"
                      onChange={(event) => update("codex_binary", event.target.value)}
                      value={settings.codex_binary}
                    />
                  </label>
                  <label className="field" htmlFor="settings-codex-model">
                    <span>{t("settings.codexModel")}</span>
                    <input
                      id="settings-codex-model"
                      onChange={(event) => update("codex_model", event.target.value)}
                      value={settings.codex_model}
                    />
                  </label>
                </div>
              </section>
            ) : null}

            <section className="settingsSection runtimeSettingsSection">
              <div className="settingsSectionHeading">
                <h3>{t("settings.runtimeSection")}</h3>
                <p>{t("settings.runtimeHint")}</p>
              </div>
              <dl className="runtimeSettingsList">
                <div>
                  <dt>{t("settings.mcpEndpoint")}</dt>
                  <dd>
                    <code>{runtimeInfo?.mcpUrl ?? t("settings.mcpUnavailable")}</code>
                  </dd>
                </div>
                <div>
                  <dt>{t("settings.dataDirectory")}</dt>
                  <dd>
                    <code>{runtimeInfo?.dataDir ?? t("settings.pathUnavailable")}</code>
                  </dd>
                </div>
              </dl>
            </section>

            <details className="settingsDisclosure advancedSettings">
              <summary>{t("settings.advanced")}</summary>
              <div className="settingsSection compactSection">
                <div className="settingsGrid threeColumns">
                  <label className="field" htmlFor="settings-embedding-batch">
                    <span>{t("settings.embeddingBatch")}</span>
                    <input
                      id="settings-embedding-batch"
                      max={2048}
                      min={1}
                      onChange={(event) =>
                        updateNumber("embedding_batch_size", event.target.valueAsNumber, 4)
                      }
                      type="number"
                      value={settings.embedding_batch_size}
                    />
                  </label>
                  <label className="field" htmlFor="settings-retrieval-top-k">
                    <span>{t("settings.retrievalTopK")}</span>
                    <input
                      id="settings-retrieval-top-k"
                      max={50}
                      min={1}
                      onChange={(event) =>
                        updateNumber("retrieval_top_k", event.target.valueAsNumber, 10)
                      }
                      type="number"
                      value={settings.retrieval_top_k}
                    />
                  </label>
                  <label className="field" htmlFor="settings-max-duration">
                    <span>{t("settings.maxDuration")}</span>
                    <input
                      id="settings-max-duration"
                      min={60}
                      onChange={(event) =>
                        updateNumber(
                          "max_audio_duration_seconds",
                          event.target.valueAsNumber,
                          21600,
                        )
                      }
                      type="number"
                      value={settings.max_audio_duration_seconds}
                    />
                  </label>
                </div>
                <div className="settingsGrid threeColumns">
                  <label className="field" htmlFor="settings-max-file">
                    <span>{t("settings.maxFileBytes")}</span>
                    <input
                      id="settings-max-file"
                      min={1}
                      onChange={(event) =>
                        updateNumber(
                          "max_remote_file_bytes",
                          event.target.valueAsNumber,
                          1073741824,
                        )
                      }
                      type="number"
                      value={settings.max_remote_file_bytes}
                    />
                  </label>
                  <label className="field" htmlFor="settings-lexical-weight">
                    <span>{t("settings.lexicalWeight")}</span>
                    <input
                      id="settings-lexical-weight"
                      max={1}
                      min={0}
                      onChange={(event) =>
                        updateNumber("retrieval_lexical_weight", event.target.valueAsNumber, 0.35)
                      }
                      step="0.05"
                      type="number"
                      value={settings.retrieval_lexical_weight}
                    />
                  </label>
                  <label className="field" htmlFor="settings-vector-weight">
                    <span>{t("settings.vectorWeight")}</span>
                    <input
                      id="settings-vector-weight"
                      max={1}
                      min={0}
                      onChange={(event) =>
                        updateNumber("retrieval_vector_weight", event.target.valueAsNumber, 0.65)
                      }
                      step="0.05"
                      type="number"
                      value={settings.retrieval_vector_weight}
                    />
                  </label>
                </div>
                <div className="settingsGrid">
                  <label className="field" htmlFor="settings-spotify-id">
                    <span>{t("settings.spotifyClientId")}</span>
                    <input
                      id="settings-spotify-id"
                      onChange={(event) => update("spotify_client_id", event.target.value)}
                      value={settings.spotify_client_id}
                    />
                  </label>
                  <label className="field" htmlFor="settings-spotify-secret">
                    <span>{t("settings.spotifyClientSecret")}</span>
                    <input
                      autoComplete="off"
                      id="settings-spotify-secret"
                      onChange={(event) => update("spotify_client_secret", event.target.value)}
                      type="password"
                      value={settings.spotify_client_secret}
                    />
                  </label>
                </div>
              </div>
            </details>
          </div>
        ) : null}

        {error ? (
          <p className="formError settingsError" role="alert">
            {error}
          </p>
        ) : null}
        <footer className="dialogActions settingsActions">
          <span>{t("settings.restartNotice")}</span>
          <button className="secondaryButton" disabled={saving} onClick={onClose} type="button">
            {t("settings.cancel")}
          </button>
          <button className="primaryButton" disabled={loading || saving} type="submit">
            {saving ? t("settings.restarting") : t("settings.saveRestart")}
          </button>
        </footer>
      </form>
    </dialog>
  );
}

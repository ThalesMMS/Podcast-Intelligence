// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DesktopSettingsDialog } from "../components/desktop-settings-dialog";
import { LocaleProvider } from "../lib/i18n/provider";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const runtimeMocks = vi.hoisted(() => ({
  getDesktopSettings: vi.fn(),
  loadRuntimeConfig: vi.fn(),
  restartDesktopEngine: vi.fn(),
  saveDesktopSettings: vi.fn(),
}));

vi.mock("../lib/runtime", () => runtimeMocks);

let activeRoot: Root | null = null;

beforeEach(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    close: {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.removeAttribute("open");
      },
    },
    showModal: {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.setAttribute("open", "");
      },
    },
  });
  vi.useFakeTimers();
  runtimeMocks.loadRuntimeConfig.mockResolvedValue({
    status: "ready",
    apiBaseUrl: "http://127.0.0.1:60597",
    apiToken: "desktop-token",
    mcpUrl: "http://127.0.0.1:60598/mcp",
    dataDir: "/tmp/podcast-intelligence",
    error: null,
  });
  runtimeMocks.restartDesktopEngine.mockResolvedValue(undefined);
  runtimeMocks.saveDesktopSettings.mockResolvedValue(undefined);
});

afterEach(async () => {
  if (activeRoot) {
    await act(async () => activeRoot?.unmount());
    activeRoot = null;
  }
  document.body.replaceChildren();
  vi.clearAllMocks();
  vi.useRealTimers();
});

async function renderSettings(settings: Record<string, unknown>) {
  runtimeMocks.getDesktopSettings.mockResolvedValue(settings);
  const container = document.createElement("div");
  document.body.append(container);
  activeRoot = createRoot(container);
  await act(async () => {
    activeRoot?.render(
      <LocaleProvider initialLocale="en-US">
        <DesktopSettingsDialog onClose={() => undefined} />
      </LocaleProvider>,
    );
  });
  return container;
}

async function changeInput(input: HTMLInputElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  await act(async () => {
    valueSetter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function changeSelect(select: HTMLSelectElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
  await act(async () => {
    valueSetter?.call(select, value);
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("DesktopSettingsDialog provider endpoints", () => {
  it("defaults to broadly compatible embedding and structured-output settings", async () => {
    const container = await renderSettings({
      ai_profile: "openai",
      transcription_provider: "openai",
      embedding_provider: "openai",
      llm_provider: "openai",
    });

    const structuredOutput = container.querySelector(
      "#settings-llm-api",
    ) as HTMLSelectElement | null;
    const sendDimensions = container.querySelector(
      "#settings-send-dimensions",
    ) as HTMLInputElement | null;

    expect(structuredOutput?.value).toBe("chat_completions");
    expect(sendDimensions?.checked).toBe(false);
  });

  it("preserves provider-specific base URLs when settings are saved", async () => {
    const container = await renderSettings({
      ai_profile: "openai",
      transcription_provider: "openai",
      embedding_provider: "openai",
      llm_provider: "openai",
      openai_base_url: "http://fallback.test/v1",
      openai_transcription_base_url: "http://transcription.test/v1",
      openai_embedding_base_url: "http://embedding.test/v1",
      openai_llm_base_url: "http://llm.test/v1",
    });

    await act(async () => {
      container
        .querySelector("form")
        ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(runtimeMocks.saveDesktopSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        openai_transcription_base_url: "http://transcription.test/v1",
        openai_embedding_base_url: "http://embedding.test/v1",
        openai_llm_base_url: "http://llm.test/v1",
      }),
    );
  });

  it("exposes all three OpenAI-compatible base URLs without a collapsed disclosure", async () => {
    const container = await renderSettings({
      ai_profile: "openai",
      transcription_provider: "openai",
      embedding_provider: "openai",
      llm_provider: "openai",
      openai_base_url: "http://fallback.test/v1",
      openai_transcription_base_url: "http://transcription.test/v1",
      openai_embedding_base_url: "http://embedding.test/v1",
      openai_llm_base_url: "http://llm.test/v1",
    });
    const expectedFields = [
      ["settings-transcription-url", "Transcription HTTP base URL", "http://transcription.test/v1"],
      ["settings-embedding-url", "Embedding base URL", "http://embedding.test/v1"],
      ["settings-llm-url", "Language-model base URL", "http://llm.test/v1"],
    ] as const;

    for (const [id, label, value] of expectedFields) {
      const input = container.querySelector(`#${id}`) as HTMLInputElement | null;
      expect(input, `${label} should be rendered`).not.toBeNull();
      expect(input?.value).toBe(value);
      expect(input?.closest("label")?.textContent).toContain(label);
      expect(input?.closest("details:not([open])")).toBeNull();
    }
  });

  it("shows the WebSocket endpoint instead of HTTP transcription fields in a hybrid profile", async () => {
    const container = await renderSettings({
      ai_profile: "custom",
      transcription_provider: "streaming_ws",
      embedding_provider: "openai",
      llm_provider: "openai",
      openai_base_url: "http://fallback.test/v1",
      openai_embedding_base_url: "http://embedding.test/v1",
      openai_llm_base_url: "http://llm.test/v1",
      streaming_stt_url: "ws://transcription.test/v1/audio/transcriptions/stream",
      streaming_stt_model: "whisper-large-v3-turbo",
    });

    expect(container.querySelector("#settings-streaming-url")).not.toBeNull();
    expect((container.querySelector("#settings-streaming-url") as HTMLInputElement).value).toBe(
      "ws://transcription.test/v1/audio/transcriptions/stream",
    );
    expect(container.querySelector("#settings-embedding-url")).not.toBeNull();
    expect(container.querySelector("#settings-llm-url")).not.toBeNull();
    expect(container.querySelector("#settings-transcription-url")).toBeNull();
    expect(container.querySelector("#settings-transcription-key")).toBeNull();
    expect(container.querySelector("#settings-transcription-model")).toBeNull();
  });

  it("migrates a stored WebSocket URL from OpenAI transcription to streaming settings", async () => {
    const container = await renderSettings({
      ai_profile: "openai",
      transcription_provider: "openai",
      embedding_provider: "openai",
      llm_provider: "openai",
      openai_transcription_base_url: "ws://transcription.test/v1/audio/transcriptions/stream",
      openai_transcription_api_key: "transcription-key",
      openai_transcription_model: "whisper-large-v3-turbo",
      openai_embedding_base_url: "http://embedding.test/v1",
      openai_llm_base_url: "http://llm.test/v1",
    });

    expect((container.querySelector("#settings-profile") as HTMLSelectElement).value).toBe(
      "custom",
    );
    expect(
      (container.querySelector("#settings-transcription-provider") as HTMLSelectElement).value,
    ).toBe("streaming_ws");
    expect((container.querySelector("#settings-streaming-url") as HTMLInputElement).value).toBe(
      "ws://transcription.test/v1/audio/transcriptions/stream",
    );
    expect((container.querySelector("#settings-streaming-key") as HTMLInputElement).value).toBe(
      "transcription-key",
    );
    expect((container.querySelector("#settings-streaming-model") as HTMLInputElement).value).toBe(
      "whisper-large-v3-turbo",
    );
    expect(container.querySelector("#settings-transcription-url")).toBeNull();

    await act(async () => {
      container
        .querySelector("form")
        ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(runtimeMocks.saveDesktopSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        ai_profile: "custom",
        transcription_provider: "streaming_ws",
        embedding_provider: "openai",
        llm_provider: "openai",
        streaming_stt_url: "ws://transcription.test/v1/audio/transcriptions/stream",
        streaming_stt_api_key: "transcription-key",
        streaming_stt_model: "whisper-large-v3-turbo",
      }),
    );
    const savedSettings = runtimeMocks.saveDesktopSettings.mock.calls.at(-1)?.[0];
    expect(savedSettings).not.toHaveProperty("openai_transcription_base_url");
    expect(savedSettings).not.toHaveProperty("openai_transcription_api_key");
  });

  it("blocks a WebSocket URL entered for an HTTP transcription provider", async () => {
    const container = await renderSettings({
      ai_profile: "openai",
      transcription_provider: "openai",
      embedding_provider: "openai",
      llm_provider: "openai",
      openai_transcription_base_url: "http://transcription.test/v1",
    });
    const transcriptionUrl = container.querySelector(
      "#settings-transcription-url",
    ) as HTMLInputElement;

    await changeInput(transcriptionUrl, "ws://transcription.test/v1/audio/transcriptions/stream");
    await act(async () => {
      container
        .querySelector("form")
        ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert?.textContent ?? "").toContain("HTTP");
    expect(runtimeMocks.saveDesktopSettings).not.toHaveBeenCalled();
    expect(runtimeMocks.restartDesktopEngine).not.toHaveBeenCalled();
  });

  it("blocks an HTTP URL entered for a WebSocket transcription provider", async () => {
    const container = await renderSettings({
      ai_profile: "custom",
      transcription_provider: "streaming_ws",
      embedding_provider: "openai",
      llm_provider: "openai",
      streaming_stt_url: "http://transcription.test/v1",
      streaming_stt_api_key: "transcription-key",
    });

    await act(async () => {
      container
        .querySelector("form")
        ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert?.textContent ?? "").toContain("WebSocket");
    expect(runtimeMocks.saveDesktopSettings).not.toHaveBeenCalled();
    expect(runtimeMocks.restartDesktopEngine).not.toHaveBeenCalled();
  });

  it("clears a protocol error after the provider configuration changes", async () => {
    const container = await renderSettings({
      ai_profile: "openai",
      transcription_provider: "openai",
      embedding_provider: "openai",
      llm_provider: "openai",
      openai_transcription_base_url: "http://transcription.test/v1",
    });
    const transcriptionUrl = container.querySelector(
      "#settings-transcription-url",
    ) as HTMLInputElement;

    await changeInput(transcriptionUrl, "ws://transcription.test/v1/audio/transcriptions/stream");
    await act(async () => {
      container
        .querySelector("form")
        ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(container.querySelector('[role="alert"]')).not.toBeNull();

    await changeSelect(container.querySelector("#settings-profile") as HTMLSelectElement, "custom");

    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

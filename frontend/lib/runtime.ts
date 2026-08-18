export interface RuntimeConfig {
  status: "starting" | "ready" | "failed";
  apiBaseUrl: string;
  apiToken: string | null;
  mcpUrl: string | null;
  dataDir: string | null;
  error: string | null;
}

const STARTUP_TIMEOUT_MS = 90_000;
const POLL_INTERVAL_MS = 250;

export function isTauriRuntime() {
  return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

async function invokeRuntime(): Promise<RuntimeConfig> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<RuntimeConfig>("runtime_config");
}

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  if (!isTauriRuntime()) {
    return {
      status: "ready",
      apiBaseUrl: import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000",
      apiToken: import.meta.env.VITE_API_TOKEN ?? null,
      mcpUrl: import.meta.env.VITE_MCP_URL ?? "http://127.0.0.1:8001/mcp",
      dataDir: null,
      error: null,
    };
  }

  const started = Date.now();
  while (Date.now() - started < STARTUP_TIMEOUT_MS) {
    const runtime = await invokeRuntime();
    if (runtime.status === "ready") return runtime;
    if (runtime.status === "failed") {
      throw new Error(runtime.error ?? "The local engine failed during startup.");
    }
    await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
  }
  throw new Error("The local processing engine did not become ready within 90 seconds.");
}

export async function getDesktopSettings(): Promise<Record<string, unknown>> {
  if (!isTauriRuntime()) return {};
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<Record<string, unknown>>("read_desktop_settings");
}

export async function saveDesktopSettings(settings: Record<string, unknown>): Promise<void> {
  if (!isTauriRuntime()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("write_desktop_settings", { settings });
}

export async function restartDesktopEngine(): Promise<void> {
  if (!isTauriRuntime()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("restart_engine");
}

export async function resetDesktopSettingsToDemo(): Promise<void> {
  if (!isTauriRuntime()) return;
  await saveDesktopSettings({
    ai_profile: "demo",
    transcription_provider: "demo",
    embedding_provider: "demo",
    llm_provider: "demo",
    desktop_job_workers: 2,
  });
  await restartDesktopEngine();
}

export async function saveTextExport(filename: string, contents: string): Promise<boolean> {
  if (!isTauriRuntime()) {
    const blob = new Blob([contents], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
    return true;
  }

  const [{ save }, { invoke }] = await Promise.all([
    import("@tauri-apps/plugin-dialog"),
    import("@tauri-apps/api/core"),
  ]);
  const extension = filename.split(".").pop()?.toLowerCase() || "txt";
  const labels: Record<string, string> = {
    md: "Markdown",
    json: "JSON",
    srt: "SubRip",
    vtt: "WebVTT",
  };
  const destination = await save({
    defaultPath: filename,
    filters: [{ name: labels[extension] ?? "Text", extensions: [extension] }],
  });
  if (!destination) return false;
  await invoke("write_export_file", { path: destination, contents });
  return true;
}

export async function openExternalUrl(url: string): Promise<void> {
  const parsed = new URL(url);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("Only HTTP and HTTPS links are supported");
  }
  if (isTauriRuntime()) {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(parsed.toString());
    return;
  }
  window.open(parsed.toString(), "_blank", "noopener,noreferrer");
}


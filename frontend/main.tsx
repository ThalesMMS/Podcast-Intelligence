import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, Route, Routes, useParams } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { Dashboard } from "@/components/dashboard";
import { EpisodeWorkspace } from "@/components/episode-workspace";
import { configureApi } from "@/lib/api";
import { LocaleProvider } from "@/lib/i18n/provider";
import {
  isTauriRuntime,
  loadRuntimeConfig,
  resetDesktopSettingsToDemo,
  type RuntimeConfig,
} from "@/lib/runtime";

import "@/app/globals.css";

function EpisodeRoute() {
  const { id } = useParams<{ id: string }>();
  return id ? <EpisodeWorkspace episodeId={id} /> : <Dashboard />;
}

function DesktopApplication() {
  const [runtime, setRuntime] = useState<RuntimeConfig | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [recovering, setRecovering] = useState(false);
  const [recoveryFailure, setRecoveryFailure] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadRuntimeConfig()
      .then((config) => {
        if (cancelled) return;
        configureApi(config.apiBaseUrl, config.apiToken);
        setRuntime(config);
      })
      .catch((error: unknown) => {
        if (!cancelled) setFailure(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failure) {
    const portuguese = navigator.language.toLowerCase().startsWith("pt");
    const title = portuguese
      ? "O Podcast Intelligence não conseguiu iniciar."
      : "Podcast Intelligence could not start.";
    const retryLabel = portuguese ? "Tentar novamente" : "Retry";
    const resetLabel = portuguese ? "Restaurar modo de demonstração" : "Reset to demo mode";
    const recoveryText = portuguese
      ? "As configurações de provedores serão substituídas pelos padrões locais. Seus episódios e arquivos serão preservados."
      : "Provider settings will be replaced with local defaults. Your episodes and files will be preserved.";

    async function recover() {
      setRecovering(true);
      setRecoveryFailure(null);
      try {
        await resetDesktopSettingsToDemo();
        window.location.reload();
      } catch (error: unknown) {
        setRecoveryFailure(error instanceof Error ? error.message : String(error));
        setRecovering(false);
      }
    }

    return (
      <div className="engineFailure" role="alert">
        <strong>{title}</strong>
        <span>{failure}</span>
        {recoveryFailure ? <span className="engineRecoveryError">{recoveryFailure}</span> : null}
        <div className="engineFailureActions">
          <button disabled={recovering} onClick={() => window.location.reload()} type="button">
            {retryLabel}
          </button>
          {isTauriRuntime() ? (
            <button
              className="secondaryEngineAction"
              disabled={recovering}
              onClick={() => void recover()}
              title={recoveryText}
              type="button"
            >
              {recovering ? "…" : resetLabel}
            </button>
          ) : null}
        </div>
        {isTauriRuntime() ? <small>{recoveryText}</small> : null}
      </div>
    );
  }
  if (!runtime) {
    const message = navigator.language.toLowerCase().startsWith("pt")
      ? "Iniciando o motor local de processamento…"
      : "Starting local processing engine…";
    return <div className="engineBoot">{message}</div>;
  }

  return (
    <HashRouter>
      <LocaleProvider>
        <AppShell>
          <Routes>
            <Route element={<Dashboard />} path="/" />
            <Route element={<EpisodeRoute />} path="/episodes/:id" />
            <Route element={<Dashboard />} path="*" />
          </Routes>
        </AppShell>
      </LocaleProvider>
    </HashRouter>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DesktopApplication />
  </StrictMode>,
);

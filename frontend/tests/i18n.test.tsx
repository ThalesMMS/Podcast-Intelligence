// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleToggle } from "../components/locale-toggle";
import { LOCALE_STORAGE_KEY } from "../lib/i18n/locales";
import { LocaleProvider, useI18n } from "../lib/i18n/provider";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;

function Probe() {
  const { locale, t, tp } = useI18n();
  return (
    <>
      <output data-active-locale={locale}>{t("shell.library")}</output>
      <span data-testid="episode-count">{tp("dashboard.episodeCount", 2, { count: 2 })}</span>
      <LocaleToggle />
    </>
  );
}

async function renderProbe() {
  const container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () =>
    root?.render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    ),
  );
  return container;
}

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  root = null;
  localStorage.clear();
  document.documentElement.lang = "";
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("LocaleProvider", () => {
  it("detects Portuguese, persists it, and updates the document language", async () => {
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("pt-PT");

    const container = await renderProbe();

    expect(container.querySelector("output")?.textContent).toBe("Biblioteca");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("pt-BR");
    expect(document.documentElement.lang).toBe("pt-BR");
  });

  it("gives stored locale precedence and switches through the accessible toggle", async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("pt-BR");
    const container = await renderProbe();
    const portuguese = container.querySelector('[data-locale="pt-BR"]') as HTMLButtonElement;

    expect(container.querySelector('[data-testid="episode-count"]')?.textContent).toBe(
      "2 episodes",
    );
    await act(async () => portuguese.click());

    expect(container.querySelector("output")?.textContent).toBe("Biblioteca");
    expect(portuguese.getAttribute("aria-pressed")).toBe("true");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("pt-BR");
  });

  it("keeps the in-memory selection when storage writes fail", async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    const container = await renderProbe();
    const portuguese = container.querySelector('[data-locale="pt-BR"]') as HTMLButtonElement;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });

    await act(async () => portuguese.click());

    expect(container.querySelector("output")?.textContent).toBe("Biblioteca");
    expect(document.documentElement.lang).toBe("pt-BR");
  });
});

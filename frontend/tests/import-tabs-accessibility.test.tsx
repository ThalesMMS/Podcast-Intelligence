// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "../components/dashboard";
import { LocaleToggle } from "../components/locale-toggle";
import { LocaleProvider } from "../lib/i18n/provider";
import { renderWithLocale } from "./i18n-test-utils";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiMocks = vi.hoisted(() => ({
  createUrlImport: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      createUrlImport: apiMocks.createUrlImport,
    },
  };
});

vi.mock("../lib/episode-polling", () => ({
  createEpisodePoller: () => ({
    start: () => undefined,
    visibilityChanged: () => undefined,
    stop: () => undefined,
  }),
}));

let activeRoot: Root | null = null;

afterEach(async () => {
  if (activeRoot) {
    await act(async () => activeRoot?.unmount());
    activeRoot = null;
  }
  document.body.replaceChildren();
  vi.clearAllMocks();
});

function openingTag(markup: string, id: string) {
  const match = markup.match(new RegExp(`<[^>]+id="${id}"[^>]*>`));
  expect(match, `element #${id} should be rendered`).not.toBeNull();
  return match?.[0] ?? "";
}

async function renderInteractiveDashboard() {
  const container = document.createElement("div");
  document.body.append(container);
  activeRoot = createRoot(container);
  await act(async () =>
    activeRoot?.render(
      <LocaleProvider initialLocale="en-US">
        <LocaleToggle />
        <Dashboard />
      </LocaleProvider>,
    ),
  );
  return container;
}

function click(element: Element) {
  act(() => element.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

function selectSource(element: HTMLSelectElement, value: string) {
  act(() => {
    element.value = value;
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function enterText(element: HTMLInputElement, value: string) {
  const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  act(() => {
    setValue?.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("import mode tabs accessibility", () => {
  it("announces File as the only initially selected and tabbable tab", () => {
    const markup = renderWithLocale(<Dashboard />);
    const fileTab = openingTag(markup, "import-tab-file");
    const urlTab = openingTag(markup, "import-tab-url");

    expect(fileTab).toContain('role="tab"');
    expect(fileTab).toContain('aria-selected="true"');
    expect(fileTab).toContain('aria-controls="import-panel-file"');
    expect(fileTab).toContain('tabindex="0"');
    expect(urlTab).toContain('aria-selected="false"');
    expect(urlTab).toContain('aria-controls="import-panel-url"');
    expect(urlTab).toContain('tabindex="-1"');
  });

  it("associates both tabpanels and hides only the inactive one", () => {
    const markup = renderWithLocale(<Dashboard />);
    const filePanel = openingTag(markup, "import-panel-file");
    const urlPanel = openingTag(markup, "import-panel-url");

    expect(filePanel).toContain('role="tabpanel"');
    expect(filePanel).toContain('aria-labelledby="import-tab-file"');
    expect(filePanel).not.toContain("hidden");
    expect(urlPanel).toContain('role="tabpanel"');
    expect(urlPanel).toContain('aria-labelledby="import-tab-url"');
    expect(urlPanel).toContain('hidden=""');
  });

  it("shows the RSS hint only for Apple Podcasts and Spotify", async () => {
    const container = await renderInteractiveDashboard();
    click(container.querySelector("#import-tab-url") as HTMLButtonElement);

    const source = container.querySelector("#import-panel-url select") as HTMLSelectElement;
    const hint = container.querySelector("#rss-url-hint") as HTMLInputElement;
    const hintField = hint.closest("label") as HTMLLabelElement;

    expect(hint.id).toBe("rss-url-hint");
    expect(hintField.textContent).toContain("Auxiliary RSS feed");
    expect(hintField.hidden).toBe(true);

    selectSource(source, "apple");
    expect(hintField.hidden).toBe(false);
    selectSource(source, "spotify");
    expect(hintField.hidden).toBe(false);
    selectSource(source, "direct_url");
    expect(hintField.hidden).toBe(true);
    selectSource(source, "rss");
    expect(hintField.hidden).toBe(true);
  });

  it("does not submit an RSS hint retained from another source", async () => {
    apiMocks.createUrlImport.mockResolvedValue({ episode_id: "episode-id", job_id: "job-id" });
    const container = await renderInteractiveDashboard();
    click(container.querySelector("#import-tab-url") as HTMLButtonElement);

    const panel = container.querySelector("#import-panel-url") as HTMLElement;
    const source = panel.querySelector("select") as HTMLSelectElement;
    const url = panel.querySelector('input[type="url"]:not(#rss-url-hint)') as HTMLInputElement;
    const hint = panel.querySelector("#rss-url-hint") as HTMLInputElement;

    selectSource(source, "spotify");
    enterText(hint, "https://stale.example/feed.xml");
    enterText(url, "https://podcast.example/feed.xml");
    selectSource(source, "rss");

    expect(hint.value).toBe("");
    await act(async () => {
      container
        .querySelector("form")
        ?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(apiMocks.createUrlImport).toHaveBeenCalledWith(
      "rss",
      "https://podcast.example/feed.xml",
      "",
      "pt",
      "",
    );
  });

  it("does not change transcription language when interface locale changes", async () => {
    const container = await renderInteractiveDashboard();
    const language = container.querySelector(".languageField select") as HTMLSelectElement;
    const portugueseLocale = container.querySelector('[data-locale="pt-BR"]') as HTMLButtonElement;

    expect(container.textContent).toContain("Podcast library");
    expect(language.value).toBe("pt");
    click(portugueseLocale);
    expect(container.textContent).toContain("Biblioteca de podcasts");
    expect(language.value).toBe("pt");
  });
});

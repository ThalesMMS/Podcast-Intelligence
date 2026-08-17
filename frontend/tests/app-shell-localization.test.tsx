import { describe, expect, it, vi } from "vitest";

import { AppShell } from "../components/app-shell";
import { renderWithLocale } from "./i18n-test-utils";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

describe("application shell localization", () => {
  it("renders English navigation and both locale choices", () => {
    const markup = renderWithLocale(
      <AppShell>
        <p>Content</p>
      </AppShell>,
    );

    expect(markup).toContain('aria-label="Primary navigation"');
    expect(markup).toContain(">Library</a>");
    expect(markup).toContain("Local workspace");
    expect(markup).toContain('data-locale="en-US"');
    expect(markup).toContain('data-locale="pt-BR"');
  });

  it("renders Portuguese navigation when requested", () => {
    const markup = renderWithLocale(
      <AppShell>
        <p>Conteúdo</p>
      </AppShell>,
      "pt-BR",
    );

    expect(markup).toContain('aria-label="Navegação principal"');
    expect(markup).toContain(">Biblioteca</a>");
    expect(markup).toContain("Workspace local");
  });
});

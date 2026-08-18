import { describe, expect, it } from "vitest";

import { Dashboard } from "../components/dashboard";
import { renderWithLocale } from "./i18n-test-utils";

describe("dashboard localization", () => {
  it("renders the full import surface in English", () => {
    const markup = renderWithLocale(<Dashboard />);

    expect(markup).toContain("Podcast library");
    expect(markup).toContain("New analysis");
    expect(markup).toContain("Transcription language");
    expect(markup).toContain("Choose an audio or video file");
  });

  it("renders the full import surface in Brazilian Portuguese", () => {
    const markup = renderWithLocale(<Dashboard />, "pt-BR");

    expect(markup).toContain("Biblioteca de podcasts");
    expect(markup).toContain("Nova análise");
    expect(markup).toContain("Idioma da transcrição");
    expect(markup).toContain("Escolher arquivo de áudio ou vídeo");
  });
});

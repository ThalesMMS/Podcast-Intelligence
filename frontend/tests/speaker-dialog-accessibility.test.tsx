import { describe, expect, it, vi } from "vitest";

import { SpeakerDialog } from "../components/speaker-dialog";
import { renderWithLocale } from "./i18n-test-utils";

describe("speaker dialog accessibility", () => {
  it("associates its accessible title, description and initial field", () => {
    const markup = renderWithLocale(
      <SpeakerDialog
        error={null}
        onClose={vi.fn()}
        onNameChange={vi.fn()}
        onSubmit={vi.fn()}
        saving={false}
        speakerName="Speaker 1"
      />,
    );

    expect(markup).toContain("<dialog");
    expect(markup).toContain('role="dialog"');
    expect(markup).toContain('aria-modal="true"');
    expect(markup).toContain('aria-labelledby="speaker-dialog-title"');
    expect(markup).toContain('aria-describedby="speaker-dialog-description"');
    expect(markup).toContain('<h2 id="speaker-dialog-title">Rename speaker</h2>');
    expect(markup).toContain('<p id="speaker-dialog-description">');
    expect(markup).toContain('for="speaker-display-name"');
    expect(markup).toContain('id="speaker-display-name"');
    expect(markup).toContain('autofocus=""');
  });

  it("announces asynchronous save errors", () => {
    const markup = renderWithLocale(
      <SpeakerDialog
        error="Could not save."
        onClose={vi.fn()}
        onNameChange={vi.fn()}
        onSubmit={vi.fn()}
        saving={false}
        speakerName="Speaker 1"
      />,
    );

    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Could not save.");
  });

  it("localizes its accessible title to Brazilian Portuguese", () => {
    const markup = renderWithLocale(
      <SpeakerDialog
        error={null}
        onClose={vi.fn()}
        onNameChange={vi.fn()}
        onSubmit={vi.fn()}
        saving={false}
        speakerName="Speaker 1"
      />,
      "pt-BR",
    );

    expect(markup).toContain('<h2 id="speaker-dialog-title">Renomear falante</h2>');
  });
});

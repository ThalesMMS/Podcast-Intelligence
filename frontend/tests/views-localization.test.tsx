import { describe, expect, it, vi } from "vitest";

import { ChatView } from "../components/chat-view";
import { SummaryView } from "../components/summary-view";
import { TranscriptView } from "../components/transcript-view";
import { renderWithLocale } from "./i18n-test-utils";

describe("episode artifact localization", () => {
  it.each([
    ["en-US", "Summary not available yet", "Transcript unavailable", "Chat with this episode"],
    [
      "pt-BR",
      "Resumo ainda não disponível",
      "Transcrição não disponível",
      "Converse com o episódio",
    ],
  ] as const)("renders empty artifacts in %s", (locale, summaryText, transcriptText, chatText) => {
    expect(
      renderWithLocale(
        <SummaryView
          episodeId="episode"
          summary={null}
          onGenerated={async () => undefined}
          onSeek={vi.fn()}
        />,
        locale,
      ),
    ).toContain(summaryText);
    expect(
      renderWithLocale(
        <TranscriptView episodeId="episode" transcript={null} onSeek={vi.fn()} />,
        locale,
      ),
    ).toContain(transcriptText);
    expect(
      renderWithLocale(<ChatView episodeId="episode" ready={false} onSeek={vi.fn()} />, locale),
    ).toContain(chatText);
  });
});

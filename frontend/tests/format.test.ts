import { describe, expect, it } from "vitest";

import { formatDuration, formatStatus } from "../lib/format";
import { catalogs, type MessageKey, type Translate } from "../lib/i18n/messages";

function translate(locale: "en-US" | "pt-BR"): Translate {
  return (key: MessageKey) => catalogs[locale][key];
}

describe("format helpers", () => {
  it("formats short and long durations", () => {
    expect(formatDuration(65_000)).toBe("1:05");
    expect(formatDuration(3_665_000)).toBe("1:01:05");
  });

  it("translates known statuses through the active catalog", () => {
    expect(formatStatus("processing", translate("en-US"))).toBe("Processing");
    expect(formatStatus("processing", translate("pt-BR"))).toBe("Processando");
    expect(formatStatus("waiting_for_user", translate("en-US"))).toBe("Waiting for user");
  });
});

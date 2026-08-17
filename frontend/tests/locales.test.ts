import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  detectBrowserLocale,
  isSupportedLocale,
  resolveLocale,
} from "../lib/i18n/locales";

describe("interface locale resolution", () => {
  it("accepts only the two supported locales", () => {
    expect(isSupportedLocale("en-US")).toBe(true);
    expect(isSupportedLocale("pt-BR")).toBe(true);
    expect(isSupportedLocale("pt")).toBe(false);
    expect(isSupportedLocale("en-GB")).toBe(false);
  });

  it.each([
    ["pt", "pt-BR"],
    ["pt-PT", "pt-BR"],
    ["PT-br", "pt-BR"],
    ["en-US", "en-US"],
    ["es-ES", "en-US"],
    [undefined, "en-US"],
  ] as const)("maps browser language %s to %s", (language, expected) => {
    expect(detectBrowserLocale(language)).toBe(expected);
  });

  it("prefers a valid stored locale", () => {
    const storage = {
      getItem: (key: string) => (key === LOCALE_STORAGE_KEY ? "en-US" : null),
    };
    expect(resolveLocale(storage, "pt-BR")).toBe("en-US");
  });

  it("ignores invalid stored values", () => {
    expect(resolveLocale({ getItem: () => "fr-FR" }, "pt-BR")).toBe("pt-BR");
  });

  it("falls back to browser detection when storage reads fail", () => {
    expect(
      resolveLocale(
        {
          getItem: () => {
            throw new DOMException("denied", "SecurityError");
          },
        },
        "en-US",
      ),
    ).toBe(DEFAULT_LOCALE);
  });
});

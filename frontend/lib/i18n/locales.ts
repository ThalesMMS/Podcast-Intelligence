export const SUPPORTED_LOCALES = ["en-US", "pt-BR"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en-US";
export const LOCALE_STORAGE_KEY = "podcast-intelligence.locale";

export function isSupportedLocale(value: unknown): value is Locale {
  return typeof value === "string" && SUPPORTED_LOCALES.some((locale) => locale === value);
}

export function detectBrowserLocale(language: string | null | undefined): Locale {
  return language?.toLowerCase().startsWith("pt") ? "pt-BR" : DEFAULT_LOCALE;
}

export function resolveLocale(
  storage: Pick<Storage, "getItem"> | null,
  browserLanguage: string | null | undefined,
): Locale {
  try {
    const stored = storage?.getItem(LOCALE_STORAGE_KEY);
    if (isSupportedLocale(stored)) return stored;
  } catch {
    return detectBrowserLocale(browserLanguage);
  }
  return detectBrowserLocale(browserLanguage);
}

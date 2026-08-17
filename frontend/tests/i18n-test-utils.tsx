import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Locale } from "../lib/i18n/locales";
import { LocaleProvider } from "../lib/i18n/provider";

export function renderWithLocale(node: ReactNode, locale: Locale = "en-US") {
  return renderToStaticMarkup(<LocaleProvider initialLocale={locale}>{node}</LocaleProvider>);
}

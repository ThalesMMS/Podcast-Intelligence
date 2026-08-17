"use client";

import { SUPPORTED_LOCALES } from "@/lib/i18n/locales";
import { useI18n } from "@/lib/i18n/provider";

export function LocaleToggle() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div className="localeToggle" role="group" aria-label={t("locale.label")}>
      {SUPPORTED_LOCALES.map((option) => (
        <button
          aria-pressed={locale === option}
          className="localeOption"
          data-locale={option}
          key={option}
          onClick={() => setLocale(option)}
          type="button"
        >
          {t(`locale.${option}`)}
        </button>
      ))}
    </div>
  );
}

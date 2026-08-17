"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";

import {
  catalogs,
  type InterpolationValues,
  type MessageKey,
  type Translate,
  type TranslatePlural,
} from "./messages";
import { DEFAULT_LOCALE, type Locale, LOCALE_STORAGE_KEY, resolveLocale } from "./locales";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Translate;
  tp: TranslatePlural;
  formatDate: (value: string | null | undefined) => string;
  formatNumber: (value: number) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function interpolate(template: string, values: InterpolationValues = {}) {
  return template.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g, (placeholder, name: string) =>
    Object.hasOwn(values, name) ? String(values[name]) : placeholder,
  );
}

function createLocaleStore(initialLocale?: Locale) {
  let currentLocale = initialLocale ?? DEFAULT_LOCALE;
  const listeners = new Set<() => void>();

  function persist(nextLocale: Locale) {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale);
    } catch {
      // Persistence is optional; the in-memory selection remains active.
    }
  }

  function updateDocument(nextLocale: Locale) {
    document.documentElement.lang = nextLocale;
  }

  function setLocale(nextLocale: Locale) {
    currentLocale = nextLocale;
    updateDocument(nextLocale);
    persist(nextLocale);
    listeners.forEach((listener) => listener());
  }

  return {
    getServerSnapshot: () => initialLocale ?? DEFAULT_LOCALE,
    getSnapshot: () => currentLocale,
    hydrate: () => {
      if (initialLocale) {
        updateDocument(initialLocale);
        return;
      }
      let storage: Pick<Storage, "getItem"> | null = null;
      try {
        storage = window.localStorage;
      } catch {
        storage = null;
      }
      setLocale(resolveLocale(storage, window.navigator.language));
    },
    setLocale,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export function LocaleProvider({
  children,
  initialLocale,
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const store = useMemo(() => createLocaleStore(initialLocale), [initialLocale]);
  const locale = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot);

  useEffect(() => {
    store.hydrate();
  }, [store]);

  const t = useCallback<Translate>(
    (key, values) => interpolate(catalogs[locale][key], values),
    [locale],
  );

  const tp = useCallback<TranslatePlural>(
    (key, count, values) => {
      const category = new Intl.PluralRules(locale).select(count) === "one" ? "one" : "other";
      return t(`${key}.${category}` as MessageKey, { count, ...values });
    },
    [locale, t],
  );

  const formatDate = useCallback(
    (value: string | null | undefined) => {
      if (!value) return t("common.dateUnavailable");
      const date = new Date(value);
      if (!Number.isFinite(date.getTime())) return t("common.dateUnavailable");
      return new Intl.DateTimeFormat(locale, {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(date);
    },
    [locale, t],
  );

  const formatNumber = useCallback(
    (value: number) => new Intl.NumberFormat(locale).format(value),
    [locale],
  );

  const context = useMemo<I18nContextValue>(
    () => ({ locale, setLocale: store.setLocale, t, tp, formatDate, formatNumber }),
    [formatDate, formatNumber, locale, store.setLocale, t, tp],
  );

  return <I18nContext.Provider value={context}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used within LocaleProvider");
  return context;
}

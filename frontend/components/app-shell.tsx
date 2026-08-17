"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { LibraryIcon, SparkIcon } from "@/components/icons";
import { LocaleToggle } from "@/components/locale-toggle";
import { useI18n } from "@/lib/i18n/provider";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useI18n();
  return (
    <div className="appShell">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Podcast Intelligence">
          <span className="brandMark">
            <SparkIcon size={19} />
          </span>
          <span>
            <strong>Podcast</strong>
            <small>Intelligence</small>
          </span>
        </Link>
        <nav className="primaryNav" aria-label={t("shell.primaryNavigation")}>
          <Link className={pathname === "/" ? "navLink active" : "navLink"} href="/">
            <LibraryIcon size={19} />
            {t("shell.library")}
          </Link>
        </nav>
        <div className="sidebarFooter">
          <LocaleToggle />
          <div className="sidebarMeta">
            <div className="environmentDot" />
            <span>{t("shell.localWorkspace")}</span>
          </div>
        </div>
      </aside>
      <main className="mainContent">{children}</main>
    </div>
  );
}

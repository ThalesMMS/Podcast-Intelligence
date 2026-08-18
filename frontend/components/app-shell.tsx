"use client";

import { Link, useLocation } from "react-router-dom";
import { type ReactNode, useRef, useState } from "react";

import { DesktopSettingsDialog } from "@/components/desktop-settings-dialog";
import { LibraryIcon, SettingsIcon, SparkIcon } from "@/components/icons";
import { LocaleToggle } from "@/components/locale-toggle";
import { useI18n } from "@/lib/i18n/provider";
import { restoreModalTriggerFocus } from "@/lib/modal-dialog";

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { t } = useI18n();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsTrigger = useRef<HTMLButtonElement>(null);

  function closeSettings() {
    setSettingsOpen(false);
    restoreModalTriggerFocus(settingsTrigger.current, null, (callback) => {
      window.setTimeout(callback, 0);
    });
  }

  return (
    <div className="appShell">
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="Podcast Intelligence">
          <span className="brandMark">
            <SparkIcon size={19} />
          </span>
          <span>
            <strong>Podcast</strong>
            <small>Intelligence</small>
          </span>
        </Link>
        <nav className="primaryNav" aria-label={t("shell.primaryNavigation")}>
          <Link className={pathname === "/" ? "navLink active" : "navLink"} to="/">
            <LibraryIcon size={19} />
            {t("shell.library")}
          </Link>
        </nav>
        <div className="sidebarFooter">
          <button
            className="settingsButton"
            onClick={() => setSettingsOpen(true)}
            ref={settingsTrigger}
            type="button"
          >
            <SettingsIcon size={17} />
            <span>{t("shell.settings")}</span>
          </button>
          <LocaleToggle />
          <div className="sidebarMeta">
            <div className="environmentDot" />
            <span>{t("shell.localWorkspace")}</span>
          </div>
        </div>
      </aside>
      <main className="mainContent">{children}</main>
      {settingsOpen ? <DesktopSettingsDialog onClose={closeSettings} /> : null}
    </div>
  );
}

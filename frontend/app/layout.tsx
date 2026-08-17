import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { LocaleProvider } from "@/lib/i18n/provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Podcast Intelligence",
  description: "Transcription, synthesis, and evidence-grounded podcast exploration.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en-US">
      <body>
        <LocaleProvider>
          <AppShell>{children}</AppShell>
        </LocaleProvider>
      </body>
    </html>
  );
}

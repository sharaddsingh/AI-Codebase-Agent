/* eslint-disable @next/next/no-page-custom-font --
   We use Google Fonts via <link> tags on purpose so that `next build` does
   not require network access. next/font/google downloads font files at
   build time; that would make CI hermetic builds harder to reproduce. */

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Codebase Agent",
  description:
    "Read-only AI agent that investigates codebases with file/line citations. Upload a folder or paste a GitHub URL to start.",
};

export const viewport: Viewport = {
  themeColor: "#0a0a0f",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
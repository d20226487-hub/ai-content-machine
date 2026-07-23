import type { Metadata } from "next";
import "./globals.css";

import { chunkReloadScript } from "@/components/ChunkReloadGuard";
import { AuthProvider } from "@/lib/auth-context";
import { LanguageProvider, langInitScript } from "@/lib/i18n-context";
import { ThemeProvider, themeInitScript } from "@/lib/theme-context";

export const metadata: Metadata = {
  title: "Content Beast",
  description: "Internal tool for AI-driven content generation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Install the chunk-load failure handler BEFORE any other
         *  script runs — when the layout's own chunk fails to fetch
         *  React never mounts, so a component-level guard would be
         *  too late. The inline script registers a window error
         *  listener during HTML parsing. */}
        <script dangerouslySetInnerHTML={{ __html: chunkReloadScript }} />
        {/* Apply theme class + lang attribute before first paint. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: langInitScript }} />
      </head>
      <body>
        <LanguageProvider>
          <ThemeProvider>
            <AuthProvider>{children}</AuthProvider>
          </ThemeProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}

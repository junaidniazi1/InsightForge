"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

/**
 * Wraps next-themes with the app's defaults:
 *   - class-based dark mode (matches `@variant dark (.dark &)` in globals.css)
 *   - system preference by default
 *   - skip transitions on theme change so the page doesn't ghost during the switch
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}

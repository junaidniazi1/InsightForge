"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Monitor, Moon, Sun } from "lucide-react";

/**
 * Cycles light → dark → system. Icon-only so it slides into the nav without
 * stealing attention. The mount guard avoids the next-themes hydration flash.
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Render a placeholder of identical size before the hook has read the
  // current theme, so the nav layout doesn't jump on hydration.
  if (!mounted) {
    return <div className="h-8 w-8" aria-hidden="true" />;
  }

  const current = theme ?? "system";
  const Icon = current === "light" ? Sun : current === "dark" ? Moon : Monitor;
  const next =
    current === "light" ? "dark" : current === "dark" ? "system" : "light";
  const label = `Theme: ${current}. Switch to ${next}.`;

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      title={label}
      aria-label={label}
      className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-muted)] transition-colors hover:border-[var(--color-border-strong)] hover:text-[var(--color-fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)]"
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

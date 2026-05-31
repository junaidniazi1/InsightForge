"use client";

import { useTheme } from "next-themes";
import { Toaster as SonnerToaster, toast } from "sonner";

/**
 * Theme-aware Sonner toaster mount. The accent colours pick from the same CSS
 * custom properties the rest of the app uses, so success/error toasts
 * automatically match the design tokens.
 */
export function Toaster() {
  const { resolvedTheme } = useTheme();
  return (
    <SonnerToaster
      theme={resolvedTheme === "dark" ? "dark" : "light"}
      richColors
      closeButton
      duration={4000}
      position="top-right"
      toastOptions={{
        classNames: {
          toast:
            "border border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-fg)] shadow-md rounded-xl",
          title: "text-sm font-medium",
          description: "text-xs text-[var(--color-muted)]",
        },
      }}
    />
  );
}

// Re-export Sonner's toast() so the rest of the app imports from one place.
export { toast };

"use client";

import { clsx } from "clsx";
import { X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  /** Body of the modal. */
  children?: ReactNode;
  /** Footer slot (right-aligned by default). */
  footer?: ReactNode;
  /** Max width — Tailwind class. Defaults to `max-w-md`. */
  size?: "sm" | "md" | "lg" | "xl";
  /** Style the title bar with a destructive accent (red tab + icon spacing). */
  destructive?: boolean;
  /** When false, the X button + click-outside + Esc are disabled. */
  dismissable?: boolean;
}

const SIZE = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
};

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Generic dialog. Backdrop + blur, centered card, animate-in, esc-to-close,
 * click-outside-to-close, lightweight focus trap that loops Tab inside the
 * dialog and restores focus when closed.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  destructive = false,
  dismissable = true,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);

  const handleClose = useCallback(() => {
    if (dismissable) onClose();
  }, [dismissable, onClose]);

  // Esc to close + Tab trap. Restore focus to whatever was active before.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = (document.activeElement as HTMLElement | null) ?? null;

    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape" && dismissable) {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const items = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute("data-focus-ignore"));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKey);

    // Focus the first focusable element when the dialog mounts.
    const t = setTimeout(() => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      const items = dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      items[0]?.focus();
    }, 0);

    // Lock body scroll while open.
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKey);
      clearTimeout(t);
      document.body.style.overflow = originalOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open, onClose, dismissable]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? "modal-title" : undefined}
      aria-describedby={description ? "modal-description" : undefined}
      onMouseDown={(e) => {
        // Click on backdrop (but not inside the dialog) closes.
        if (e.target === e.currentTarget) handleClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-modal-fade"
    >
      <div
        ref={dialogRef}
        className={clsx(
          "w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] shadow-xl",
          "animate-modal-in",
          SIZE[size],
        )}
      >
        {destructive && (
          <div className="h-1 bg-[var(--color-danger)]" aria-hidden="true" />
        )}
        <div className="flex items-start justify-between gap-4 px-5 pt-5">
          <div className="min-w-0">
            {title && (
              <h2
                id="modal-title"
                className={clsx(
                  "text-base font-semibold",
                  destructive ? "text-[var(--color-danger)]" : "text-[var(--color-fg)]",
                )}
              >
                {title}
              </h2>
            )}
            {description && (
              <p id="modal-description" className="mt-1 text-xs text-[var(--color-muted)]">
                {description}
              </p>
            )}
          </div>
          {dismissable && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1 text-[var(--color-muted)] transition-colors hover:bg-[var(--color-bg)] hover:text-[var(--color-fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-ring)]"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        {children !== undefined && (
          <div className="px-5 py-4 text-sm text-[var(--color-fg)]">{children}</div>
        )}
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-bg)]/40 px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

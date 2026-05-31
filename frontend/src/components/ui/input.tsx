import { clsx } from "clsx";
import { forwardRef, type InputHTMLAttributes } from "react";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  /** Optional error message rendered below the input in rose. */
  error?: string;
  /** Optional helper line rendered below the input in muted. */
  hint?: string;
}

const CONTROL_BASE =
  "block w-full rounded-lg border bg-[var(--color-panel)] px-3 text-sm text-[var(--color-fg)] " +
  "placeholder:text-[var(--color-muted)] transition-colors outline-none " +
  "focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-ring)]/30 " +
  "disabled:cursor-not-allowed disabled:opacity-60 disabled:bg-[var(--color-bg)]";

const CONTROL_OK = "border-[var(--color-border)]";
const CONTROL_ERR =
  "border-[var(--color-danger)] focus:border-[var(--color-danger)] focus:ring-[var(--color-danger)]/30";

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { className, error, hint, id, ...rest },
  ref,
) {
  const inputId = id ?? rest.name;
  return (
    <div className="space-y-1">
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={
          error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined
        }
        {...rest}
        className={clsx(CONTROL_BASE, "h-9 py-2", error ? CONTROL_ERR : CONTROL_OK, className)}
      />
      {error ? (
        <p id={`${inputId}-error`} className="text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-xs text-[var(--color-muted)]">
          {hint}
        </p>
      ) : null}
    </div>
  );
});

// Re-export the class string + ok/err helpers so Select + Textarea share the
// exact same look without duplicating the styling.
export const CONTROL_CLASS_BASE = CONTROL_BASE;
export const CONTROL_CLASS_OK = CONTROL_OK;
export const CONTROL_CLASS_ERR = CONTROL_ERR;

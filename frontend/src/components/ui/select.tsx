import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";
import { forwardRef, type SelectHTMLAttributes } from "react";
import {
  CONTROL_CLASS_BASE,
  CONTROL_CLASS_ERR,
  CONTROL_CLASS_OK,
} from "./input";

interface Props extends SelectHTMLAttributes<HTMLSelectElement> {
  error?: string;
  hint?: string;
}

/** Native <select> styled to match Input. Chevron is a decorative overlay. */
export const Select = forwardRef<HTMLSelectElement, Props>(function Select(
  { className, error, hint, id, children, ...rest },
  ref,
) {
  const selectId = id ?? rest.name;
  return (
    <div className="space-y-1">
      <div className="relative">
        <select
          ref={ref}
          id={selectId}
          aria-invalid={error ? true : undefined}
          aria-describedby={
            error ? `${selectId}-error` : hint ? `${selectId}-hint` : undefined
          }
          {...rest}
          className={clsx(
            CONTROL_CLASS_BASE,
            "h-9 appearance-none pr-8",
            error ? CONTROL_CLASS_ERR : CONTROL_CLASS_OK,
            className,
          )}
        >
          {children}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted)]"
        />
      </div>
      {error ? (
        <p id={`${selectId}-error`} className="text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : hint ? (
        <p id={`${selectId}-hint`} className="text-xs text-[var(--color-muted)]">
          {hint}
        </p>
      ) : null}
    </div>
  );
});

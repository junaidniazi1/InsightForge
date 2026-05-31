import { clsx } from "clsx";
import { forwardRef, type TextareaHTMLAttributes } from "react";
import {
  CONTROL_CLASS_BASE,
  CONTROL_CLASS_ERR,
  CONTROL_CLASS_OK,
} from "./input";

interface Props extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: string;
  hint?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, Props>(function Textarea(
  { className, error, hint, id, rows = 4, ...rest },
  ref,
) {
  const txtId = id ?? rest.name;
  return (
    <div className="space-y-1">
      <textarea
        ref={ref}
        id={txtId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={
          error ? `${txtId}-error` : hint ? `${txtId}-hint` : undefined
        }
        {...rest}
        className={clsx(
          CONTROL_CLASS_BASE,
          "py-2",
          error ? CONTROL_CLASS_ERR : CONTROL_CLASS_OK,
          className,
        )}
      />
      {error ? (
        <p id={`${txtId}-error`} className="text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : hint ? (
        <p id={`${txtId}-hint`} className="text-xs text-[var(--color-muted)]">
          {hint}
        </p>
      ) : null}
    </div>
  );
});

import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

interface Props extends HTMLAttributes<HTMLDivElement> {
  /** Optional hover affordance for clickable / linked cards. */
  interactive?: boolean;
  /** Switch the inner padding. Default `md` (p-6). */
  padding?: "none" | "sm" | "md" | "lg";
}

const PADDING: Record<NonNullable<Props["padding"]>, string> = {
  none: "p-0",
  sm: "p-3",
  md: "p-6",
  lg: "p-8",
};

export function Card({
  className,
  interactive = false,
  padding = "md",
  ...rest
}: Props) {
  return (
    <div
      {...rest}
      className={clsx(
        "rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] shadow-sm transition-colors",
        interactive && "hover-lift cursor-pointer",
        PADDING[padding],
        className,
      )}
    />
  );
}

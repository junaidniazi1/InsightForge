import Link from "next/link";
import { clsx } from "clsx";
import type { ReactNode } from "react";

interface CTA {
  label: string;
  href?: string;
  /** Used when the action is in-page (not a navigation). */
  onClick?: () => void;
}

interface Props {
  /** Lucide icon, sized via className `h-X w-X` by the caller. */
  icon?: ReactNode;
  title: string;
  description?: string;
  cta?: CTA;
  secondary?: CTA;
  className?: string;
}

/**
 * Used wherever a list is empty or a tool doesn't apply to the current data.
 * Reuse keeps the empty experience consistent across Sources, Dashboards,
 * Connections, and the disabled-state workbench tabs.
 */
export function EmptyState({
  icon,
  title,
  description,
  cta,
  secondary,
  className,
}: Props) {
  return (
    <div
      className={clsx(
        "flex flex-col items-center rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-panel)] px-6 py-10 text-center",
        className,
      )}
    >
      {icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-bg)] text-[var(--color-muted)]">
          {icon}
        </div>
      )}
      <h3 className="text-base font-medium text-[var(--color-fg)]">{title}</h3>
      {description && (
        <p className="mt-1 max-w-md text-sm text-[var(--color-muted)]">
          {description}
        </p>
      )}
      {(cta || secondary) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {cta && <CTAButton cta={cta} primary />}
          {secondary && <CTAButton cta={secondary} />}
        </div>
      )}
    </div>
  );
}

function CTAButton({ cta, primary = false }: { cta: CTA; primary?: boolean }) {
  const cls = primary
    ? "inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[var(--color-accent-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)]"
    : "inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-4 text-sm font-medium text-[var(--color-fg)] shadow-sm transition-colors hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg)]";
  if (cta.href) {
    return (
      <Link href={cta.href} className={cls}>
        {cta.label}
      </Link>
    );
  }
  return (
    <button type="button" onClick={cta.onClick} className={cls}>
      {cta.label}
    </button>
  );
}

import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import type { ReactNode } from "react";

interface Breadcrumb {
  label: string;
  href: string;
}

interface Props {
  title: string;
  description?: string;
  /** Single back-link (e.g. "← Sources"). */
  back?: Breadcrumb;
  /** Right-side slot for primary actions (Button / button group). */
  actions?: ReactNode;
}

/**
 * Consistent page top across every authenticated route. Use this instead of
 * re-rolling a header on each page. Title + description + optional back link +
 * actions on the right.
 */
export function PageHeader({ title, description, back, actions }: Props) {
  return (
    <header className="animate-fade-in-up flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] pb-4">
      <div className="min-w-0 flex-1">
        {back && (
          <Link
            href={back.href}
            className="inline-flex items-center gap-1 text-xs text-[var(--color-muted)] transition-colors hover:text-[var(--color-fg)]"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            {back.label}
          </Link>
        )}
        <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight text-[var(--color-fg)]">
          {title}
        </h1>
        {description && (
          <p className="mt-1 text-sm text-[var(--color-muted)]">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </header>
  );
}

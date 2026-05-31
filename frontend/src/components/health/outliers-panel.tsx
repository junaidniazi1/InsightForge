import { clsx } from "clsx";
import type { OutlierGroups, Severity } from "@/types";
import { SeverityBadge } from "./severity-badge";

interface Props {
  outliers: OutlierGroups;
}

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? n.toString() : n.toFixed(digits);
}

function SubPanel({
  title,
  badge,
  description,
  empty,
  children,
}: {
  title: string;
  badge: "per-column" | "multivariate";
  description: string;
  empty?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border bg-[var(--color-panel)]">
      <header className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium">{title}</h3>
          <span
            className={clsx(
              "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
              badge === "per-column"
                ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
                : "border-violet-500/40 bg-violet-500/10 text-violet-300"
            )}
          >
            {badge === "per-column" ? "single-column" : "multivariate"}
          </span>
        </div>
        <p className="mt-1 text-xs text-[var(--color-muted)]">{description}</p>
      </header>
      <div className="p-4">
        {empty ? (
          <p className="text-xs text-[var(--color-muted)]">
            No outliers flagged by this method.
          </p>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

export function OutliersPanel({ outliers }: Props) {
  const { iqr, zscore, isolation_forest: iso } = outliers;

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel)]/50 p-3 text-xs text-[var(--color-muted)]">
        <strong className="font-medium text-[var(--color-fg)]">Why three groups?</strong> Per-column
        methods (IQR, Z-score) look at one column at a time and disagree on what counts as extreme;
        Isolation Forest looks at all numeric columns jointly and can flag rows where every individual
        value looks fine but the *combination* is unusual. They are reported separately because the
        rows they flag are usually different.
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {/* --- IQR --- */}
        <SubPanel
          title="Per-column: IQR"
          badge="per-column"
          description={iqr.method_description}
          empty={iqr.columns.length === 0}
        >
          <ul className="space-y-3">
            {iqr.columns.map((c) => (
              <li key={c.column} className="space-y-1 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono">{c.column}</span>
                  <SeverityBadge severity={c.severity as Severity} />
                </div>
                <p className="text-xs text-[var(--color-muted)]">
                  {c.outlier_count} row(s) outside [{fmt(c.lower_bound)}, {fmt(c.upper_bound)}] · {c.outlier_pct}%
                </p>
                <p className="text-[10px] text-[var(--color-muted)]">
                  suggested: <span className="text-[var(--color-fg)]">{c.suggested_fix}</span>
                </p>
              </li>
            ))}
          </ul>
        </SubPanel>

        {/* --- Z-score --- */}
        <SubPanel
          title="Per-column: Z-score"
          badge="per-column"
          description={zscore.method_description}
          empty={zscore.columns.length === 0}
        >
          <ul className="space-y-3">
            {zscore.columns.map((c) => (
              <li key={c.column} className="space-y-1 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono">{c.column}</span>
                  <SeverityBadge severity={c.severity as Severity} />
                </div>
                <p className="text-xs text-[var(--color-muted)]">
                  {c.outlier_count} row(s) with |z| &gt; {c.threshold} · {c.outlier_pct}%
                </p>
                <p className="text-[10px] text-[var(--color-muted)]">
                  μ={fmt(c.mean)} · σ={fmt(c.std)} · suggested:{" "}
                  <span className="text-[var(--color-fg)]">{c.suggested_fix}</span>
                </p>
              </li>
            ))}
          </ul>
        </SubPanel>

        {/* --- Isolation Forest --- */}
        <SubPanel
          title="Multivariate: Isolation Forest"
          badge="multivariate"
          description={iso.method_description}
          empty={iso.available && (iso.outlier_row_count ?? 0) === 0}
        >
          {!iso.available ? (
            <p className="text-xs text-[var(--color-muted)]">
              Not run: {iso.reason ?? "no numeric columns."}
            </p>
          ) : (
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span>{iso.outlier_row_count} anomalous row(s)</span>
                {iso.severity && <SeverityBadge severity={iso.severity} />}
              </div>
              <p className="text-xs text-[var(--color-muted)]">
                {iso.outlier_row_pct}% of {iso.fitted_on_rows} rows fitted
                {iso.sampled ? " (sampled)" : ""}
              </p>
              {iso.numeric_columns_used && iso.numeric_columns_used.length > 0 && (
                <p className="text-[10px] text-[var(--color-muted)]">
                  fitted across:{" "}
                  <span className="font-mono">{iso.numeric_columns_used.join(", ")}</span>
                </p>
              )}
              {iso.row_indices_sample && iso.row_indices_sample.length > 0 && (
                <details className="text-[10px]">
                  <summary className="cursor-pointer text-[var(--color-muted)]">
                    Sample of flagged row indices
                  </summary>
                  <p className="mt-1 break-all font-mono text-[var(--color-muted)]">
                    {iso.row_indices_sample.slice(0, 40).join(", ")}
                    {iso.row_indices_sample.length > 40 ? "…" : ""}
                  </p>
                </details>
              )}
              <p className="text-[10px] text-[var(--color-muted)]">
                suggested: <span className="text-[var(--color-fg)]">{iso.suggested_fix}</span>
              </p>
            </div>
          )}
        </SubPanel>
      </div>
    </div>
  );
}

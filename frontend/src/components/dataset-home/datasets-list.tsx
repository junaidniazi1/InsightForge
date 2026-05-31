"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  BarChart3,
  Database,
  Heart,
  Search,
  Sparkles,
  Wrench,
  Wand2,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { Dataset } from "@/types";
import { DatasetRowActions } from "./dataset-row-actions";

interface Props {
  datasets: Dataset[];
}

const STATUS_VARIANT: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  uploaded: "info",
  profiling: "warning",
  profiled: "success",
  cleaned: "success",
  error: "danger",
};

/**
 * Client-side filtered, icon-decorated dataset list. The Sources server
 * component fetches the rows; this component owns the search box, empty
 * state, and per-row action chips.
 */
export function DatasetsList({ datasets }: Props) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query.trim()) return datasets;
    const q = query.trim().toLowerCase();
    return datasets.filter((d) => d.name.toLowerCase().includes(q));
  }, [datasets, query]);

  if (datasets.length === 0) {
    return (
      <EmptyState
        icon={<Database className="h-5 w-5" />}
        title="No datasets yet"
        description="Upload a CSV or Excel file above to profile, clean, dashboard, and explain it with AI."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted)]"
          aria-hidden="true"
        />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${datasets.length} dataset${datasets.length === 1 ? "" : "s"}…`}
          className="pl-9"
        />
      </div>

      {filtered.length === 0 ? (
        <Card padding="md" className="text-center text-sm text-[var(--color-muted)]">
          No datasets match <span className="font-mono">&quot;{query}&quot;</span>.
        </Card>
      ) : (
        <ul className="divide-y divide-[var(--color-border)] overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] shadow-sm">
          {filtered.map((ds) => (
            <li
              key={ds.id}
              className="flex items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-[var(--color-bg)]"
            >
              <Link href={`/sources/${ds.id}`} className="min-w-0 flex-1">
                <p className="truncate font-medium text-[var(--color-fg)]">
                  {ds.name}
                </p>
                <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                  {ds.source_type === "file_csv"
                    ? "CSV"
                    : ds.source_type === "file_excel"
                      ? "Excel"
                      : "DB"}{" "}
                  · {new Date(ds.created_at).toLocaleString()}
                  {ds.row_count !== null && (
                    <> · {ds.row_count.toLocaleString()} rows</>
                  )}
                </p>
              </Link>
              <div className="flex shrink-0 items-center gap-1.5">
                <ActionLink href={`/sources/${ds.id}/health`} icon={<Heart className="h-3.5 w-3.5" />} label="Health" />
                <ActionLink href={`/sources/${ds.id}/clean`} icon={<Wand2 className="h-3.5 w-3.5" />} label="Clean" />
                <ActionLink href={`/sources/${ds.id}/dashboard`} icon={<BarChart3 className="h-3.5 w-3.5" />} label="Dashboard" />
                <ActionLink href={`/sources/${ds.id}/ai`} icon={<Sparkles className="h-3.5 w-3.5" />} label="AI" />
                <ActionLink href={`/sources/${ds.id}/workbench`} icon={<Wrench className="h-3.5 w-3.5" />} label="Workbench" />
                <Badge variant={STATUS_VARIANT[ds.status] ?? "neutral"} compact>
                  {ds.status}
                </Badge>
                <DatasetRowActions datasetId={ds.id} datasetName={ds.name} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ActionLink({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      title={label}
      aria-label={label}
      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-muted)] transition-colors hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg)] hover:text-[var(--color-fg)]"
    >
      {icon}
    </Link>
  );
}

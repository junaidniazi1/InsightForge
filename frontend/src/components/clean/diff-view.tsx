"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { clsx } from "clsx";
import { apiGet } from "@/lib/api";
import type { CleanResponse, ProfileEnvelope } from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DownloadButtons } from "@/components/dataset-home/download-buttons";

interface Props {
  datasetId: string;
  response: CleanResponse;
  onStartOver: () => void;
}

const POLL_MS = 2000;

function ScoreBadge({ score, label }: { score: number | null; label: string }) {
  const color =
    score === null
      ? "text-[var(--color-muted)]"
      : score >= 85
        ? "text-[var(--color-success)]"
        : score >= 60
          ? "text-amber-400"
          : "text-[var(--color-danger)]";
  return (
    <div className="rounded-md border bg-[var(--color-bg)]/40 px-3 py-2 text-center">
      <p className={clsx("text-2xl font-semibold", color)}>{score ?? "…"}</p>
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-muted)]">{label}</p>
    </div>
  );
}

function Delta({ before, after, lower_is_better = false }: {
  before: number; after: number; lower_is_better?: boolean;
}) {
  const delta = after - before;
  if (delta === 0) return <span className="text-[var(--color-muted)]">±0</span>;
  const better = lower_is_better ? delta < 0 : delta > 0;
  const sign = delta > 0 ? "+" : "";
  return (
    <span className={better ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}>
      {sign}{delta.toLocaleString()}
    </span>
  );
}

export function DiffView({ datasetId, response, onStartOver }: Props) {
  const { diff, quality_score_before } = response;
  const [afterScore, setAfterScore] = useState<number | null>(null);
  const [reprofileFailed, setReprofileFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const tick = async () => {
      try {
        const r = await apiGet<ProfileEnvelope>(
          `/datasets/${datasetId}/profile?version_id=${response.cleaned_version_id}`
        );
        if (cancelled) return;
        if (r.status === "ready" && r.profile?.summary?.quality_score !== undefined) {
          setAfterScore(r.profile.summary.quality_score);
          return; // stop polling
        }
        if (r.status === "failed") {
          setReprofileFailed(true);
          return;
        }
        attempts += 1;
        if (attempts < 60) setTimeout(tick, POLL_MS);
      } catch {
        if (cancelled) return;
        attempts += 1;
        if (attempts < 60) setTimeout(tick, POLL_MS);
      }
    };
    void tick();
    return () => {
      cancelled = true;
    };
  }, [datasetId, response.cleaned_version_id]);

  return (
    <div className="space-y-6">
      {/* "You're done" affordance — first thing the user sees on success. */}
      <Card className="border-[var(--color-success)]/40 bg-[var(--color-success)]/5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-medium text-[var(--color-success)]">
              You’re done — download your cleaned data
            </h2>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              The raw upload is untouched. Cleaned version saved as v{response.version_no}
              ({response.steps_applied.length} step{response.steps_applied.length === 1 ? "" : "s"}).
            </p>
          </div>
          <DownloadButtons
            datasetId={datasetId}
            versionId={response.cleaned_version_id}
            label="Download"
          />
        </div>
      </Card>

      {/* Headline */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-success)]">
              Cleaned version saved
            </p>
            <h2 className="mt-1 text-xl font-semibold">
              Version {response.version_no} · {response.steps_applied.length} step(s) applied
            </h2>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              <span className="font-mono">{response.storage_path}</span>
            </p>
          </div>
          <div className="flex items-center gap-3">
            <ScoreBadge score={quality_score_before ?? null} label="Before" />
            <span className="text-lg text-[var(--color-muted)]">→</span>
            <ScoreBadge score={afterScore} label="After" />
          </div>
        </div>
        {!afterScore && !reprofileFailed && (
          <p className="mt-4 text-xs text-[var(--color-muted)]">
            Re-profiling the cleaned version in the background to compute the new quality score…
          </p>
        )}
        {reprofileFailed && (
          <p className="mt-4 text-xs text-[var(--color-danger)]">
            Re-profile failed. The cleaned version was still saved.
          </p>
        )}
      </Card>

      {/* Numeric diff */}
      <Card>
        <h3 className="mb-4 text-sm font-medium">Summary diff</h3>
        <div className="grid gap-4 text-sm md:grid-cols-2 lg:grid-cols-4">
          <DiffStat label="Rows"
            before={diff.rows_before} after={diff.rows_after} />
          <DiffStat label="Columns"
            before={diff.columns_before} after={diff.columns_after} />
          <DiffStat label="Duplicate rows" lowerIsBetter
            before={diff.duplicates_before} after={diff.duplicates_after} />
          <DiffStat label="Total nulls" lowerIsBetter
            before={Object.values(diff.null_counts).reduce((s, n) => s + n.before, 0)}
            after={Object.values(diff.null_counts).reduce((s, n) => s + n.after, 0)} />
        </div>

        {(diff.columns_added.length > 0 || diff.columns_dropped.length > 0) && (
          <div className="mt-6 grid gap-4 text-sm md:grid-cols-2">
            {diff.columns_added.length > 0 && (
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  Columns added
                </p>
                <p className="mt-1 break-all font-mono text-[var(--color-success)]">
                  {diff.columns_added.join(", ")}
                </p>
              </div>
            )}
            {diff.columns_dropped.length > 0 && (
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  Columns dropped
                </p>
                <p className="mt-1 break-all font-mono text-[var(--color-danger)]">
                  {diff.columns_dropped.join(", ")}
                </p>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Per-column nulls */}
      <Card>
        <h3 className="mb-4 text-sm font-medium">Per-column null counts</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="border-b">
              <tr className="text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                <th className="py-2 pr-4">Column</th>
                <th className="py-2 pr-4">Before</th>
                <th className="py-2 pr-4">After</th>
                <th className="py-2 pr-4">Δ</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(diff.null_counts)
                .filter(([, n]) => n.before !== n.after || n.before > 0)
                .sort(([, a], [, b]) => b.before - a.before)
                .map(([col, n]) => (
                  <tr key={col} className="border-b last:border-0">
                    <td className="py-2 pr-4 font-mono text-xs">{col}</td>
                    <td className="py-2 pr-4">{n.before.toLocaleString()}</td>
                    <td className="py-2 pr-4">{n.after.toLocaleString()}</td>
                    <td className="py-2 pr-4">
                      <Delta before={n.before} after={n.after} lower_is_better />
                    </td>
                  </tr>
                ))}
              {Object.values(diff.null_counts).every((n) => n.before === 0 && n.after === 0) && (
                <tr>
                  <td colSpan={4} className="py-3 text-xs text-[var(--color-muted)]">
                    No nulls in any common column.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Changed rows sample */}
      {diff.changed_rows_sample.length > 0 && (
        <Card>
          <h3 className="mb-4 text-sm font-medium">
            Sample of changed rows ({diff.changed_rows_sample.length})
          </h3>
          <div className="space-y-4">
            {diff.changed_rows_sample.map((row) => (
              <ChangedRowDiff key={row.index} row={row} />
            ))}
          </div>
        </Card>
      )}

      {/* Pipeline log */}
      <Card>
        <h3 className="mb-3 text-sm font-medium">Pipeline log</h3>
        <ol className="space-y-2 text-xs">
          {response.steps_applied.map((s, i) => (
            <li key={i} className="rounded border bg-[var(--color-bg)]/40 px-3 py-2">
              <p className="font-mono text-[var(--color-muted)]">
                {i + 1}. {String(s.op)}
                {Array.isArray(s.columns) && (s.columns as string[]).length > 0 && (
                  <span> on {(s.columns as string[]).join(", ")}</span>
                )}
              </p>
              {typeof s.summary === "string" && (
                <p className="mt-1 text-[var(--color-fg)]">{s.summary}</p>
              )}
            </li>
          ))}
        </ol>
      </Card>

      {/* Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="secondary" onClick={onStartOver}>
          Build another pipeline
        </Button>
        <div className="flex items-center gap-2">
          <Link
            href={`/sources/${datasetId}`}
            className="text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
          >
            Back to dataset
          </Link>
          <span className="rounded border px-3 py-1.5 text-sm text-[var(--color-muted)]">
            Dashboard · Phase 4
          </span>
        </div>
      </div>
    </div>
  );
}

function DiffStat({
  label,
  before,
  after,
  lowerIsBetter = false,
}: {
  label: string;
  before: number;
  after: number;
  lowerIsBetter?: boolean;
}) {
  return (
    <div className="rounded-md border bg-[var(--color-bg)]/40 px-3 py-2">
      <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">{label}</p>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <p className="font-mono text-sm">
          {before.toLocaleString()} → {after.toLocaleString()}
        </p>
        <Delta before={before} after={after} lower_is_better={lowerIsBetter} />
      </div>
    </div>
  );
}

function ChangedRowDiff({ row }: { row: import("@/types").ChangedRow }) {
  const cols = Array.from(new Set([...Object.keys(row.before), ...Object.keys(row.after)]));
  return (
    <div className="rounded-md border bg-[var(--color-bg)]/40 p-3">
      <p className="mb-2 text-xs text-[var(--color-muted)]">row index {row.index}</p>
      <div className="grid gap-1 text-xs md:grid-cols-2">
        <div className="space-y-0.5">
          {cols.map((c) => {
            const before = row.before[c];
            const after = row.after[c];
            const changed = JSON.stringify(before) !== JSON.stringify(after);
            return (
              <p key={c} className={changed ? "text-[var(--color-danger)]" : "text-[var(--color-muted)]"}>
                <span className="font-mono">{c}:</span>{" "}
                {before === null || before === undefined ? "null" : String(before)}
              </p>
            );
          })}
        </div>
        <div className="space-y-0.5">
          {cols.map((c) => {
            const before = row.before[c];
            const after = row.after[c];
            const changed = JSON.stringify(before) !== JSON.stringify(after);
            return (
              <p key={c} className={changed ? "text-[var(--color-success)]" : "text-[var(--color-muted)]"}>
                <span className="font-mono">{c}:</span>{" "}
                {after === null || after === undefined ? "null" : String(after)}
              </p>
            );
          })}
        </div>
      </div>
    </div>
  );
}

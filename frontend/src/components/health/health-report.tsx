"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type {
  AcceptedFix,
  Issue,
  Profile,
  ProfileEnvelope,
  ProfileTriggerResponse,
  Severity,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ColumnDetails } from "./column-details";
import { IssueCard } from "./issue-card";
import { OutliersPanel } from "./outliers-panel";
import { QualityScore } from "./quality-score";
import { SeverityBadge } from "./severity-badge";

interface Props {
  datasetId: string;
}

interface FixSelection {
  fix: string;
  accepted: boolean;
}

const POLL_MS = 1500;
const SEVERITIES: Severity[] = ["high", "medium", "low"];

function stashKey(datasetId: string): string {
  return `insightforge:accepted_fixes:${datasetId}`;
}

export function HealthReport({ datasetId }: Props) {
  const [envelope, setEnvelope] = useState<ProfileEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selections, setSelections] = useState<Record<string, FixSelection>>({});
  const [stashedAt, setStashedAt] = useState<string | null>(null);
  const triggeredRef = useRef(false);

  // ----- Load + poll ------------------------------------------------------
  const fetchOnce = useCallback(async () => {
    try {
      const r = await apiGet<ProfileEnvelope>(`/datasets/${datasetId}/profile`);
      setEnvelope(r);
      setError(null);
      return r;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [datasetId]);

  const trigger = useCallback(async () => {
    try {
      await apiPost<ProfileTriggerResponse>(`/datasets/${datasetId}/profile`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [datasetId]);

  // Initial fetch + auto-trigger
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const r = await fetchOnce();
      if (cancelled || !r) return;
      if (r.status === "needs_profiling" && !triggeredRef.current) {
        triggeredRef.current = true;
        await trigger();
        await fetchOnce();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchOnce, trigger]);

  // Polling while a job is in flight
  useEffect(() => {
    if (envelope?.status !== "running") return;
    const t = setInterval(() => void fetchOnce(), POLL_MS);
    return () => clearInterval(t);
  }, [envelope?.status, fetchOnce]);

  // ----- Hydrate selections when profile arrives --------------------------
  useEffect(() => {
    const profile = envelope?.profile;
    if (!profile) return;
    setSelections((prev) => {
      const next: Record<string, FixSelection> = { ...prev };
      for (const issue of profile.issues) {
        if (!next[issue.id]) {
          next[issue.id] = { fix: issue.suggested_fix, accepted: false };
        }
      }
      return next;
    });
  }, [envelope?.profile]);

  const profile: Profile | null = envelope?.profile ?? null;

  const issuesBySeverity = useMemo(() => {
    const buckets: Record<Severity, Issue[]> = { high: [], medium: [], low: [] };
    if (!profile) return buckets;
    for (const issue of profile.issues) buckets[issue.severity].push(issue);
    return buckets;
  }, [profile]);

  const acceptedFixes: AcceptedFix[] = useMemo(() => {
    if (!profile) return [];
    return profile.issues
      .filter((i) => selections[i.id]?.accepted)
      .map((i) => ({
        issue_id: i.id,
        column: i.column,
        issue_type: i.issue_type,
        fix: selections[i.id].fix,
      }));
  }, [profile, selections]);

  function onFixChange(issueId: string, fix: string) {
    setSelections((s) => ({ ...s, [issueId]: { fix, accepted: s[issueId]?.accepted ?? false } }));
  }
  function onAcceptChange(issueId: string, accepted: boolean) {
    setSelections((s) => ({
      ...s,
      [issueId]: { fix: s[issueId]?.fix ?? "", accepted },
    }));
  }

  function onReviewAndClean() {
    // Stash the accepted fixes for the cleaning page to seed from.
    const payload = { datasetId, capturedAt: new Date().toISOString(), fixes: acceptedFixes };
    try {
      localStorage.setItem(stashKey(datasetId), JSON.stringify(payload));
      setStashedAt(payload.capturedAt);
    } catch {
      // localStorage can throw in private mode; the cleaning page can still be opened manually.
    }
    window.location.href = `/sources/${datasetId}/clean`;
  }

  // ----- Render states ----------------------------------------------------
  if (error && !envelope) {
    return (
      <Card>
        <p className="text-sm text-[var(--color-danger)]">Couldn’t load profile: {error}</p>
        <Button className="mt-3" onClick={() => void fetchOnce()}>
          Retry
        </Button>
      </Card>
    );
  }

  if (!envelope) {
    return <p className="text-sm text-[var(--color-muted)]">Loading…</p>;
  }

  if (envelope.status === "needs_profiling" || envelope.status === "running") {
    return (
      <Card>
        <div className="flex items-center gap-3">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-[var(--color-accent)]" />
          <p className="text-sm">
            Profiling your dataset… this runs in the background and usually takes a few seconds.
          </p>
        </div>
        {envelope.job?.created_at && (
          <p className="mt-2 text-xs text-[var(--color-muted)]">
            Job started {new Date(envelope.job.created_at).toLocaleTimeString()} ·{" "}
            status {envelope.job.status}
          </p>
        )}
      </Card>
    );
  }

  if (envelope.status === "failed") {
    return (
      <Card>
        <p className="text-sm text-[var(--color-danger)]">
          Profiling failed: {envelope.error ?? "unknown error"}
        </p>
        <Button
          className="mt-3"
          onClick={async () => {
            triggeredRef.current = false;
            await trigger();
            await fetchOnce();
          }}
        >
          Retry profiling
        </Button>
      </Card>
    );
  }

  if (!profile) return null;

  const { summary, columns, outliers } = profile;

  return (
    <div className="space-y-8">
      {/* ---- Summary header ---- */}
      <Card>
        <div className="grid gap-6 md:grid-cols-[auto_1fr]">
          <QualityScore score={summary.quality_score} breakdown={summary.quality_breakdown} />
          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <Stat label="Rows" value={summary.row_count.toLocaleString()} />
            <Stat label="Columns" value={summary.column_count.toString()} />
            <Stat
              label="Missing cells"
              value={`${summary.overall_missing_pct}%`}
              accent={summary.overall_missing_pct > 5 ? "warn" : "ok"}
            />
            <Stat
              label="Duplicate rows"
              value={summary.duplicate_row_count.toLocaleString()}
              accent={summary.duplicate_row_count > 0 ? "warn" : "ok"}
            />
            <Stat label="High issues" value={issuesBySeverity.high.length.toString()} />
            <Stat label="Medium" value={issuesBySeverity.medium.length.toString()} />
            <Stat label="Low" value={issuesBySeverity.low.length.toString()} />
            <Stat
              label="Profiled"
              value={
                envelope.profiled_at
                  ? new Date(envelope.profiled_at).toLocaleString()
                  : "—"
              }
            />
          </div>
        </div>
        {summary.sampled && (
          <p className="mt-4 text-xs text-amber-400">
            Large file: profile based on the first {summary.sample_rows_used.toLocaleString()} rows.
          </p>
        )}
      </Card>

      {/* ---- Issues ---- */}
      <section className="space-y-4">
        <header className="flex items-center justify-between">
          <h2 className="text-lg font-medium">
            Issues ({profile.issues.length})
          </h2>
          <p className="text-xs text-[var(--color-muted)]">
            Pick a fix and toggle Accept. Nothing is applied until Phase 3.
          </p>
        </header>
        {profile.issues.length === 0 ? (
          <Card>
            <p className="text-sm text-[var(--color-success)]">
              No issues detected — this dataset looks clean.
            </p>
          </Card>
        ) : (
          SEVERITIES.map((sev) => {
            const list = issuesBySeverity[sev];
            if (list.length === 0) return null;
            return (
              <div key={sev} className="space-y-3">
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={sev} />
                  <span className="text-xs text-[var(--color-muted)]">{list.length}</span>
                </div>
                <div className="space-y-3">
                  {list.map((issue) => {
                    const sel = selections[issue.id] ?? {
                      fix: issue.suggested_fix,
                      accepted: false,
                    };
                    return (
                      <IssueCard
                        key={issue.id}
                        issue={issue}
                        selectedFix={sel.fix}
                        accepted={sel.accepted}
                        onFixChange={(f) => onFixChange(issue.id, f)}
                        onAcceptChange={(a) => onAcceptChange(issue.id, a)}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })
        )}
      </section>

      {/* ---- Outliers ---- */}
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Outliers</h2>
        <OutliersPanel outliers={outliers} />
      </section>

      {/* ---- Per-column details ---- */}
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Per-column details ({columns.length})</h2>
        <ColumnDetails columns={columns} />
      </section>

      {/* ---- Review & clean (Phase 3 will consume) ---- */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm">
              {acceptedFixes.length} fix{acceptedFixes.length === 1 ? "" : "es"} selected for cleaning.
            </p>
            {stashedAt && (
              <p className="mt-1 text-xs text-[var(--color-success)]">
                Captured at {new Date(stashedAt).toLocaleTimeString()}. Phase 3 will apply these.
              </p>
            )}
          </div>
          <Button disabled={acceptedFixes.length === 0} onClick={onReviewAndClean}>
            Review &amp; clean →
          </Button>
        </div>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  accent = "neutral",
}: {
  label: string;
  value: string;
  accent?: "ok" | "warn" | "neutral";
}) {
  const color =
    accent === "ok"
      ? "text-[var(--color-success)]"
      : accent === "warn"
        ? "text-amber-400"
        : "text-[var(--color-fg)]";
  return (
    <div>
      <p className="text-xs text-[var(--color-muted)]">{label}</p>
      <p className={`mt-0.5 text-sm font-medium ${color}`}>{value}</p>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import type {
  AcceptedFix,
  CleanResponse,
  CleanStep,
  OperationCatalog,
  OperationCatalogItem,
  PreviewResponse,
  ProfileEnvelope,
  SemanticType,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AutoCleanButton } from "./auto-clean-button";
import { DiffView } from "./diff-view";
import { StepCard } from "./step-card";
import { Toolbox } from "./toolbox";

interface Props {
  datasetId: string;
}

// Phase-2 fix strings that mean "user chose not to change anything" — skip
// these when seeding the pipeline so we don't add no-op steps.
const NOOP_FIXES = new Set(["keep", "leave_as_is", "review"]);

function stashKey(datasetId: string): string {
  return `insightforge:accepted_fixes:${datasetId}`;
}

export function CleanPage({ datasetId }: Props) {
  const [catalog, setCatalog] = useState<OperationCatalog | null>(null);
  const [columns, setColumns] = useState<{ name: string; semantic_type?: SemanticType }[]>([]);
  const [pipeline, setPipeline] = useState<CleanStep[]>([]);
  const [stashApplied, setStashApplied] = useState(false);
  const [seededCount, setSeededCount] = useState<number>(0);

  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [result, setResult] = useState<CleanResponse | null>(null);

  // Auto-clean output (Phase 6).
  const [autoExplanation, setAutoExplanation] = useState<string | null>(null);
  const [autoSummary, setAutoSummary] = useState<string | null>(null);

  // ----- catalog + columns ------------------------------------------------
  useEffect(() => {
    apiGet<OperationCatalog>(`/datasets/${datasetId}/operations`).then(setCatalog).catch(() => {
      setCatalog({ groups: {} });
    });
  }, [datasetId]);

  useEffect(() => {
    // Try profile (has semantic types); fall back to preview for raw column names.
    apiGet<ProfileEnvelope>(`/datasets/${datasetId}/profile`)
      .then((env) => {
        if (env.profile) {
          setColumns(
            env.profile.columns.map((c) => ({ name: c.name, semantic_type: c.semantic_type }))
          );
          return;
        }
        return apiGet<PreviewResponse>(
          `/datasets/${datasetId}/preview?page=1&page_size=1`
        ).then((p) => setColumns(p.columns.map((name) => ({ name }))));
      })
      .catch(() => {
        // Last-ditch fallback so the page still works.
        apiGet<PreviewResponse>(`/datasets/${datasetId}/preview?page=1&page_size=1`)
          .then((p) => setColumns(p.columns.map((name) => ({ name }))))
          .catch(() => undefined);
      });
  }, [datasetId]);

  // ----- seed pipeline from Phase-2 stash ---------------------------------
  useEffect(() => {
    if (stashApplied) return;
    try {
      const raw = localStorage.getItem(stashKey(datasetId));
      if (!raw) {
        setStashApplied(true);
        return;
      }
      const payload = JSON.parse(raw) as { fixes?: AcceptedFix[] };
      const seeded: CleanStep[] = (payload.fixes ?? [])
        .filter((f) => !NOOP_FIXES.has(f.fix))
        .map((f) => ({
          op: f.fix,
          columns: f.column ? [f.column] : [],
          params: {},
        }));
      setPipeline(seeded);
      setSeededCount(seeded.length);
    } catch {
      // ignore
    } finally {
      setStashApplied(true);
    }
  }, [datasetId, stashApplied]);

  // ----- pipeline mutators ------------------------------------------------
  const move = useCallback((i: number, dir: -1 | 1) => {
    setPipeline((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const copy = prev.slice();
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  }, []);

  const remove = useCallback((i: number) => {
    setPipeline((prev) => prev.filter((_, k) => k !== i));
  }, []);

  const updateStep = useCallback((i: number, next: CleanStep) => {
    setPipeline((prev) => prev.map((s, k) => (k === i ? next : s)));
  }, []);

  const addStep = useCallback((step: CleanStep) => {
    setPipeline((prev) => [...prev, step]);
  }, []);

  // Catalog lookup by id (across all groups).
  const opIndex = useMemo<Map<string, OperationCatalogItem>>(() => {
    const m = new Map<string, OperationCatalogItem>();
    if (!catalog) return m;
    for (const group of Object.values(catalog.groups)) {
      for (const op of group ?? []) m.set(op.id, op);
    }
    return m;
  }, [catalog]);

  // ----- apply ------------------------------------------------------------
  async function applyPipeline() {
    if (pipeline.length === 0) return;
    setApplying(true);
    setApplyError(null);
    try {
      const r = await apiPost<CleanResponse>(
        `/datasets/${datasetId}/clean`,
        { steps: pipeline }
      );
      setResult(r);
      // Clear stash so re-opening the page starts fresh.
      try {
        localStorage.removeItem(stashKey(datasetId));
      } catch {
        // ignore
      }
    } catch (e) {
      setApplyError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplying(false);
    }
  }

  // ----- render -----------------------------------------------------------
  if (result) {
    return (
      <DiffView
        datasetId={datasetId}
        response={result}
        onStartOver={() => {
          setResult(null);
          setPipeline([]);
        }}
      />
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_460px]">
      {/* ---- Pipeline ---- */}
      <div className="space-y-4">
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium">Pipeline ({pipeline.length})</h2>
              <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                Steps apply in order, top to bottom. Reorder with ↑/↓.
                {seededCount > 0 && stashApplied && (
                  <> Seeded {seededCount} step{seededCount === 1 ? "" : "s"} from Data Health.</>
                )}
              </p>
              {autoSummary && (
                <p className="mt-1 text-xs text-[var(--color-accent)]">
                  Auto-clean: {autoSummary}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <AutoCleanButton
                datasetId={datasetId}
                onPlan={(steps, explanation, summary) => {
                  setPipeline(steps);
                  setAutoExplanation(explanation);
                  setAutoSummary(summary);
                }}
              />
              <Button
                onClick={applyPipeline}
                disabled={applying || pipeline.length === 0}
              >
                {applying ? "Applying…" : `Apply pipeline (${pipeline.length})`}
              </Button>
            </div>
          </div>
          {autoExplanation && (
            <p className="mt-3 rounded border bg-[var(--color-bg)]/40 p-2 text-xs text-[var(--color-muted)]">
              {autoExplanation}
            </p>
          )}
          {applyError && (
            <p className="mt-3 rounded border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-2 text-xs text-[var(--color-danger)]">
              {applyError}
            </p>
          )}
        </Card>

        {pipeline.length === 0 ? (
          <Card>
            <p className="text-sm text-[var(--color-muted)]">
              Pipeline is empty. Add an operation from the toolbox, or accept fixes on the{" "}
              <Link
                href={`/sources/${datasetId}/health`}
                className="text-[var(--color-accent)] hover:underline"
              >
                Data Health page
              </Link>
              .
            </p>
          </Card>
        ) : (
          <div className="space-y-3">
            {pipeline.map((step, i) => (
              <StepCard
                key={i}
                index={i}
                total={pipeline.length}
                step={step}
                op={opIndex.get(step.op) ?? null}
                columns={columns}
                onMove={(dir) => move(i, dir)}
                onRemove={() => remove(i)}
                onChange={(next) => updateStep(i, next)}
              />
            ))}
          </div>
        )}
      </div>

      {/* ---- Toolbox ---- */}
      <Toolbox
        datasetId={datasetId}
        catalog={catalog}
        columns={columns}
        onAdd={addStep}
      />
    </div>
  );
}

"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type { AutoPlanResponse, CleanStep } from "@/types";
import { Button } from "@/components/ui/button";

interface Props {
  datasetId: string;
  /** Called with the planned steps (CleanStep[]). */
  onPlan: (steps: CleanStep[], explanation: string | null, summary: string) => void;
}

export function AutoCleanButton({ datasetId, onPlan }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<AutoPlanResponse>(`/datasets/${datasetId}/clean/auto-plan`);
      const steps: CleanStep[] = r.steps.map((s) => ({
        op: s.op,
        columns: s.columns,
        params: s.params,
        rationale: s.rationale,
      }));
      onPlan(steps, r.explanation ?? null, r.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Button onClick={run} disabled={busy} className="text-sm">
        {busy ? "Planning…" : "✨ Auto-clean"}
      </Button>
      {error && (
        <span className="text-xs text-[var(--color-danger)]">{error}</span>
      )}
    </div>
  );
}

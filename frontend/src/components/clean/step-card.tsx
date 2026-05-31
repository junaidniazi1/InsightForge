"use client";

import { useState } from "react";
import type { CleanStep, OperationCatalogItem } from "@/types";
import { Button } from "@/components/ui/button";
import { ParamForm } from "./param-form";

interface Props {
  index: number;
  total: number;
  step: CleanStep;
  op: OperationCatalogItem | null;
  columns: { name: string; semantic_type?: string }[];
  onMove: (dir: -1 | 1) => void;
  onRemove: () => void;
  onChange: (next: CleanStep) => void;
}

export function StepCard({ index, total, step, op, columns, onMove, onRemove, onChange }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border bg-[var(--color-panel)]">
      <header className="flex items-start gap-3 px-4 py-3">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-[var(--color-bg)] text-xs font-mono">
          {index + 1}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{op?.label ?? step.op}</p>
          <p className="mt-0.5 text-xs text-[var(--color-muted)]">
            {step.columns.length > 0 ? (
              <>columns: <span className="font-mono">{step.columns.join(", ")}</span></>
            ) : (
              "no columns"
            )}
            {Object.keys(step.params).length > 0 && (
              <>
                {" · "}
                <span className="font-mono">{JSON.stringify(step.params)}</span>
              </>
            )}
          </p>
          {step.rationale && (
            <p className="mt-1 text-xs text-[var(--color-accent)]">
              <span className="text-[var(--color-muted)]">why:</span> {step.rationale}
            </p>
          )}
          {!op && (
            <p className="mt-1 text-xs text-amber-400">
              Op <span className="font-mono">{step.op}</span> not in catalog — will still be sent but
              params can&apos;t be edited here.
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            onClick={() => onMove(-1)}
            disabled={index === 0}
            className="rounded border px-1.5 py-0.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)] disabled:opacity-30"
            aria-label="Move up"
          >
            ↑
          </button>
          <button
            onClick={() => onMove(1)}
            disabled={index === total - 1}
            className="rounded border px-1.5 py-0.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)] disabled:opacity-30"
            aria-label="Move down"
          >
            ↓
          </button>
          {op && (
            <button
              onClick={() => setOpen((o) => !o)}
              className="rounded border px-1.5 py-0.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            >
              {open ? "Done" : "Edit"}
            </button>
          )}
          <button
            onClick={onRemove}
            className="rounded border border-[var(--color-danger)]/40 px-1.5 py-0.5 text-xs text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10"
          >
            ✕
          </button>
        </div>
      </header>
      {open && op && (
        <div className="border-t px-4 py-3">
          <ParamForm op={op} columns={columns} value={step} onChange={onChange} />
        </div>
      )}
    </div>
  );
}

"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import { apiPost } from "@/lib/api";
import type {
  CleanPreviewResponse,
  CleanStep,
  OpGroup,
  OperationCatalog,
  OperationCatalogItem,
} from "@/types";
import { Button } from "@/components/ui/button";
import { ParamForm } from "./param-form";

interface Props {
  datasetId: string;
  catalog: OperationCatalog | null;
  columns: { name: string; semantic_type?: string }[];
  onAdd: (step: CleanStep) => void;
}

const GROUP_ORDER: OpGroup[] = ["core", "text", "datetime", "column", "transform"];
const GROUP_LABELS: Record<OpGroup, string> = {
  core: "Core",
  text: "Text & categorical",
  datetime: "Datetime",
  column: "Columns",
  transform: "Transformations (optional)",
};

export function Toolbox({ datasetId, catalog, columns, onAdd }: Props) {
  const [group, setGroup] = useState<OpGroup>("core");
  const [selected, setSelected] = useState<OperationCatalogItem | null>(null);
  const [step, setStep] = useState<CleanStep | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<CleanPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const groups = useMemo<OpGroup[]>(
    () => GROUP_ORDER.filter((g) => (catalog?.groups[g] ?? []).length > 0),
    [catalog]
  );
  const items = catalog?.groups[group] ?? [];

  function pick(item: OperationCatalogItem) {
    setSelected(item);
    setStep({ op: item.id, columns: [], params: {} });
    setPreview(null);
    setPreviewError(null);
  }

  async function runPreview() {
    if (!step) return;
    setPreviewing(true);
    setPreviewError(null);
    try {
      const r = await apiPost<CleanPreviewResponse>(
        `/datasets/${datasetId}/clean/preview`,
        { step }
      );
      setPreview(r);
      if (r.error) setPreviewError(r.error);
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : String(e));
    } finally {
      setPreviewing(false);
    }
  }

  function addToPipeline() {
    if (!step) return;
    onAdd(step);
    setSelected(null);
    setStep(null);
    setPreview(null);
  }

  return (
    <aside className="rounded-lg border bg-[var(--color-panel)]">
      <header className="border-b px-4 py-3">
        <h2 className="text-sm font-medium">Add operation</h2>
      </header>

      {/* Group tabs */}
      <nav className="flex flex-wrap gap-1 border-b px-3 py-2 text-xs">
        {groups.map((g) => (
          <button
            key={g}
            onClick={() => {
              setGroup(g);
              setSelected(null);
              setStep(null);
              setPreview(null);
            }}
            className={clsx(
              "rounded px-2 py-1",
              g === group
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            )}
          >
            {GROUP_LABELS[g]}
          </button>
        ))}
      </nav>

      {group === "transform" && (
        <p className="border-b bg-amber-500/10 px-4 py-2 text-xs text-amber-300">
          Optional — for modelling. Don’t apply by accident; these change values and shapes.
        </p>
      )}

      <div className="grid gap-0 md:grid-cols-[200px_1fr]">
        {/* Op list */}
        <ul className="max-h-96 overflow-y-auto border-r text-sm">
          {items.map((it) => (
            <li key={it.id}>
              <button
                onClick={() => pick(it)}
                className={clsx(
                  "block w-full px-3 py-2 text-left text-xs hover:bg-[var(--color-border)]/30",
                  selected?.id === it.id && "bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                )}
              >
                {it.label}
              </button>
            </li>
          ))}
        </ul>

        {/* Editor */}
        <div className="min-w-0 p-4">
          {!selected || !step ? (
            <p className="text-xs text-[var(--color-muted)]">
              Pick an operation to configure it.
            </p>
          ) : (
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-medium">{selected.label}</h3>
                <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                  {selected.description}
                </p>
              </div>
              <ParamForm op={selected} columns={columns} value={step} onChange={setStep} />
              <div className="flex flex-wrap items-center gap-2 border-t pt-3">
                <Button variant="secondary" onClick={runPreview} disabled={previewing}>
                  {previewing ? "Previewing…" : "Preview"}
                </Button>
                <Button onClick={addToPipeline}>Add to pipeline</Button>
              </div>
              {previewError && (
                <p className="text-xs text-[var(--color-danger)]">{previewError}</p>
              )}
              {preview && !preview.error && (
                <PreviewTable preview={preview} />
              )}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function PreviewTable({ preview }: { preview: CleanPreviewResponse }) {
  const allCols = Array.from(new Set([...preview.columns_before, ...preview.columns_after]));
  const beforeByIdx = preview.sample_before;
  const afterByIdx = preview.sample_after;
  const maxLen = Math.max(beforeByIdx.length, afterByIdx.length);

  function cell(rows: Record<string, unknown>[], i: number, c: string): string {
    const row = rows[i];
    if (!row) return "—";
    const v = row[c];
    if (v === null || v === undefined) return "null";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }

  return (
    <div className="rounded-md border bg-[var(--color-bg)]/60">
      <div className="border-b px-3 py-2 text-xs">
        <span className="text-[var(--color-muted)]">Sample dry-run · </span>
        <span>{preview.summary ?? preview.op}</span>
      </div>
      <div className="grid grid-cols-2 divide-x text-[11px]">
        <div className="overflow-x-auto">
          <p className="px-3 py-1 text-[var(--color-muted)]">before</p>
          <table className="min-w-full">
            <thead className="bg-[var(--color-bg)]/40">
              <tr>
                {allCols.map((c) => (
                  <th key={c} className="whitespace-nowrap px-2 py-1 text-left font-mono font-normal">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: maxLen }).map((_, i) => (
                <tr key={i} className="border-t">
                  {allCols.map((c) => (
                    <td key={c} className="whitespace-nowrap px-2 py-1 text-[var(--color-muted)]">
                      {cell(beforeByIdx, i, c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="overflow-x-auto">
          <p className="px-3 py-1 text-[var(--color-muted)]">after</p>
          <table className="min-w-full">
            <thead className="bg-[var(--color-bg)]/40">
              <tr>
                {allCols.map((c) => (
                  <th key={c} className="whitespace-nowrap px-2 py-1 text-left font-mono font-normal">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: maxLen }).map((_, i) => (
                <tr key={i} className="border-t">
                  {allCols.map((c) => (
                    <td key={c} className="whitespace-nowrap px-2 py-1">
                      {cell(afterByIdx, i, c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

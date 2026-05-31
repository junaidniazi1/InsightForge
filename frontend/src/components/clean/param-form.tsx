"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  CleanStep,
  OpParamSchema,
  OperationCatalogItem,
} from "@/types";
import { Input } from "@/components/ui/input";

interface Props {
  op: OperationCatalogItem;
  columns: { name: string; semantic_type?: string }[];
  value: CleanStep;
  onChange: (next: CleanStep) => void;
}

function defaultFor(p: OpParamSchema): unknown {
  if (p.default !== undefined) return p.default;
  switch (p.type) {
    case "boolean":
      return false;
    case "number":
      return 0;
    case "list":
      return [];
    case "mapping":
      return {};
    default:
      return "";
  }
}

function tryParseMapping(text: string): { ok: true; value: Record<string, string> } | { ok: false; error: string } {
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return { ok: false, error: "Mapping must be a JSON object." };
    }
    return { ok: true, value: parsed as Record<string, string> };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "invalid JSON" };
  }
}

function parseListString(text: string): string[] {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function ParamForm({ op, columns, value, onChange }: Props) {
  const needsColumns = op.applies_to !== "dataset";

  // Initialise missing param defaults when the op changes.
  useEffect(() => {
    const next: Record<string, unknown> = { ...value.params };
    let changed = false;
    for (const p of op.params) {
      if (next[p.name] === undefined) {
        next[p.name] = defaultFor(p);
        changed = true;
      }
    }
    if (changed) onChange({ ...value, params: next });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [op.id]);

  const recommendedCols = useMemo(() => {
    if (op.applies_to === "any" || op.applies_to === "dataset") return columns.map((c) => c.name);
    const matchSet =
      op.applies_to === "categorical"
        ? new Set(["categorical", "boolean"])
        : new Set([op.applies_to]);
    return columns.filter((c) => c.semantic_type && matchSet.has(c.semantic_type)).map((c) => c.name);
  }, [op.applies_to, columns]);

  function setParam(name: string, val: unknown) {
    onChange({ ...value, params: { ...value.params, [name]: val } });
  }
  function toggleColumn(name: string) {
    const has = value.columns.includes(name);
    onChange({
      ...value,
      columns: has ? value.columns.filter((c) => c !== name) : [...value.columns, name],
    });
  }

  return (
    <div className="space-y-4">
      {needsColumns && (
        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
            Column(s)
            {op.applies_to !== "any" && (
              <span className="ml-2 text-[10px]">(recommended: {op.applies_to})</span>
            )}
          </label>
          <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border bg-[var(--color-bg)] p-2">
            {columns.length === 0 ? (
              <p className="text-xs text-[var(--color-muted)]">No columns loaded yet.</p>
            ) : (
              columns.map((c) => {
                const recommended = recommendedCols.includes(c.name);
                const checked = value.columns.includes(c.name);
                return (
                  <label
                    key={c.name}
                    className="flex cursor-pointer items-center gap-2 rounded px-1 text-xs hover:bg-[var(--color-border)]/30"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleColumn(c.name)}
                      className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                    />
                    <span className="font-mono">{c.name}</span>
                    {c.semantic_type && (
                      <span
                        className={
                          recommended
                            ? "text-[10px] text-[var(--color-accent)]"
                            : "text-[10px] text-[var(--color-muted)]"
                        }
                      >
                        {c.semantic_type}
                      </span>
                    )}
                  </label>
                );
              })
            )}
          </div>
        </div>
      )}

      {op.params.map((p) => (
        <ParamInput
          key={p.name}
          schema={p}
          value={value.params[p.name]}
          onChange={(v) => setParam(p.name, v)}
        />
      ))}
    </div>
  );
}

function ParamInput({
  schema,
  value,
  onChange,
}: {
  schema: OpParamSchema;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const [mappingText, setMappingText] = useState<string>(() =>
    schema.type === "mapping" && typeof value === "object" && value !== null
      ? JSON.stringify(value, null, 2)
      : ""
  );
  const [mappingErr, setMappingErr] = useState<string | null>(null);

  function commonLabel() {
    return (
      <label className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
        {schema.label}
        {schema.description && (
          <span className="ml-2 font-normal text-[10px]">{schema.description}</span>
        )}
      </label>
    );
  }

  if (schema.type === "boolean") {
    return (
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 accent-[var(--color-accent)]"
        />
        <span>{schema.label}</span>
      </label>
    );
  }
  if (schema.type === "select") {
    return (
      <div>
        {commonLabel()}
        <select
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 text-sm"
        >
          {(schema.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (schema.type === "number") {
    return (
      <div>
        {commonLabel()}
        <Input
          type="number"
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        />
      </div>
    );
  }
  if (schema.type === "list") {
    // Multi-select if options provided; otherwise comma-separated text.
    if (schema.options && schema.options.length) {
      const selected = new Set(Array.isArray(value) ? (value as string[]) : []);
      return (
        <div>
          {commonLabel()}
          <div className="flex flex-wrap gap-2">
            {schema.options.map((o) => {
              const on = selected.has(o);
              return (
                <button
                  type="button"
                  key={o}
                  onClick={() => {
                    const next = new Set(selected);
                    if (on) next.delete(o);
                    else next.add(o);
                    onChange(Array.from(next));
                  }}
                  className={
                    "rounded-full border px-2 py-0.5 text-xs " +
                    (on
                      ? "border-[var(--color-accent)] bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                      : "text-[var(--color-muted)] hover:text-[var(--color-fg)]")
                  }
                >
                  {o}
                </button>
              );
            })}
          </div>
        </div>
      );
    }
    const text = Array.isArray(value) ? (value as unknown[]).join(", ") : String(value ?? "");
    return (
      <div>
        {commonLabel()}
        <Input
          value={text}
          onChange={(e) => onChange(parseListString(e.target.value))}
          placeholder="comma, separated, values"
        />
      </div>
    );
  }
  if (schema.type === "mapping") {
    return (
      <div>
        {commonLabel()}
        <textarea
          value={mappingText}
          onChange={(e) => {
            setMappingText(e.target.value);
            const r = tryParseMapping(e.target.value);
            if (r.ok) {
              setMappingErr(null);
              onChange(r.value);
            } else {
              setMappingErr(r.error);
            }
          }}
          placeholder={'{ "usa": "US", "United States": "US" }'}
          rows={5}
          className="w-full rounded-md border bg-[var(--color-bg)] px-2 py-1 font-mono text-xs"
        />
        {mappingErr && (
          <p className="mt-1 text-xs text-[var(--color-danger)]">{mappingErr}</p>
        )}
      </div>
    );
  }
  return (
    <div>
      {commonLabel()}
      <Input
        value={typeof value === "string" ? value : value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

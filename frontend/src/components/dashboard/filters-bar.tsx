"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import type { FilterClause, FilterOption } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Props {
  options: FilterOption[];
  value: FilterClause[];
  onChange: (next: FilterClause[]) => void;
}

const MAX_COLLAPSED = 4; // show this many filters before "more"

export function FiltersBar({ options, value, onChange }: Props) {
  const [expanded, setExpanded] = useState(false);

  // Only show columns the user has opted into as active filters, plus a fixed
  // suggested set so the bar is useful out of the box.
  const ordered = useMemo(() => {
    const priority: Record<string, number> = {
      categorical: 0,
      datetime_range: 1,
      numeric_range: 2,
    };
    return options.slice().sort((a, b) => priority[a.kind] - priority[b.kind]);
  }, [options]);

  const shown = expanded ? ordered : ordered.slice(0, MAX_COLLAPSED);
  const byCol = new Map(value.map((c) => [c.column, c]));

  function setClause(col: string, next: FilterClause | null) {
    const others = value.filter((c) => c.column !== col);
    onChange(next ? [...others, next] : others);
  }

  function clearAll() {
    onChange([]);
  }

  if (options.length === 0) {
    return (
      <p className="text-xs text-[var(--color-muted)]">No filterable columns detected.</p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        {shown.map((opt) => (
          <FilterControl
            key={opt.column}
            option={opt}
            value={byCol.get(opt.column)}
            onChange={(next) => setClause(opt.column, next)}
          />
        ))}
        {ordered.length > MAX_COLLAPSED && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
          >
            {expanded ? "Fewer filters" : `${ordered.length - MAX_COLLAPSED} more…`}
          </button>
        )}
        {value.length > 0 && (
          <Button variant="ghost" onClick={clearAll} className="ml-auto text-xs">
            Clear filters
          </Button>
        )}
      </div>
    </div>
  );
}

function FilterControl({
  option,
  value,
  onChange,
}: {
  option: FilterOption;
  value: FilterClause | undefined;
  onChange: (next: FilterClause | null) => void;
}) {
  if (option.kind === "categorical") {
    const selected = new Set(((value?.values as string[]) ?? []).map(String));
    return (
      <div className="min-w-[180px]">
        <label className="mb-1 block text-xs text-[var(--color-muted)]">
          {option.column}
        </label>
        <div className="flex max-w-md flex-wrap gap-1 rounded border bg-[var(--color-panel)] p-1">
          {(option.values ?? []).slice(0, 50).map((v) => {
            const on = selected.has(v);
            return (
              <button
                key={v}
                type="button"
                onClick={() => {
                  const next = new Set(selected);
                  if (on) next.delete(v);
                  else next.add(v);
                  if (next.size === 0) onChange(null);
                  else onChange({ column: option.column, type: "in", values: Array.from(next) });
                }}
                className={clsx(
                  "max-w-[180px] truncate rounded px-2 py-0.5 text-[11px]",
                  on
                    ? "bg-[var(--color-accent)]/30 text-[var(--color-accent)]"
                    : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                )}
              >
                {v}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // numeric_range or datetime_range: two inputs
  const isDate = option.kind === "datetime_range";
  const inputType = isDate ? "date" : "number";

  const dateValue = (v: unknown): string => {
    if (typeof v !== "string") return "";
    return v.slice(0, 10);
  };
  const numValue = (v: unknown): string => {
    if (typeof v === "number") return String(v);
    if (typeof v === "string") return v;
    return "";
  };

  function applyChange(next: { min?: unknown; max?: unknown }) {
    const merged = { min: value?.min, max: value?.max, ...next };
    if (
      (merged.min === undefined || merged.min === "" || merged.min === null) &&
      (merged.max === undefined || merged.max === "" || merged.max === null)
    ) {
      onChange(null);
      return;
    }
    onChange({
      column: option.column,
      type: "range",
      min: merged.min === "" ? null : (merged.min as number | string | null | undefined) ?? null,
      max: merged.max === "" ? null : (merged.max as number | string | null | undefined) ?? null,
    });
  }

  return (
    <div className="min-w-[180px]">
      <label className="mb-1 block text-xs text-[var(--color-muted)]">{option.column}</label>
      <div className="flex items-center gap-1">
        <Input
          type={inputType}
          placeholder={isDate ? dateValue(option.min) : numValue(option.min)}
          value={isDate ? dateValue(value?.min) : numValue(value?.min)}
          onChange={(e) => applyChange({ min: e.target.value })}
          className="text-xs"
        />
        <span className="text-[var(--color-muted)]">–</span>
        <Input
          type={inputType}
          placeholder={isDate ? dateValue(option.max) : numValue(option.max)}
          value={isDate ? dateValue(value?.max) : numValue(value?.max)}
          onChange={(e) => applyChange({ max: e.target.value })}
          className="text-xs"
        />
      </div>
    </div>
  );
}

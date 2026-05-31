"use client";

import { useState } from "react";
import type { DashboardListItem } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Props {
  saved: DashboardListItem[];
  currentName: string;
  currentId: string | null;
  onNameChange: (name: string) => void;
  onSave: () => Promise<void>;
  onOpen: (id: string) => void;
  onDelete: (id: string) => Promise<void>;
  onNew: () => void;
}

export function SaveLoad({
  saved,
  currentName,
  currentId,
  onNameChange,
  onSave,
  onOpen,
  onDelete,
  onNew,
}: Props) {
  const [saving, setSaving] = useState(false);
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 rounded-lg border bg-[var(--color-panel)] p-3">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="mb-1 block text-xs text-[var(--color-muted)]">Dashboard name</label>
          <Input
            value={currentName}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="My dashboard"
            className="min-w-[200px]"
          />
        </div>
        <Button
          onClick={async () => {
            setSaving(true);
            try {
              await onSave();
            } finally {
              setSaving(false);
            }
          }}
          disabled={!currentName.trim() || saving}
        >
          {saving ? "Saving…" : currentId ? "Save changes" : "Save dashboard"}
        </Button>
        <Button variant="ghost" onClick={onNew}>
          New
        </Button>
      </div>
      {saved.length > 0 && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="mb-1 block text-xs text-[var(--color-muted)]">
            Open saved ({saved.length})
          </label>
          <select
            value={currentId ?? ""}
            onChange={(e) => e.target.value && onOpen(e.target.value)}
            className="rounded-md border bg-[var(--color-bg)] px-2 py-1.5 text-sm"
          >
            <option value="">— pick —</option>
            {saved.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} · {d.chart_count} chart{d.chart_count === 1 ? "" : "s"}
              </option>
            ))}
          </select>
          {currentId && (
            <Button
              variant="danger"
              onClick={() => {
                if (window.confirm("Delete this dashboard?")) void onDelete(currentId);
              }}
              className="text-xs"
            >
              Delete
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

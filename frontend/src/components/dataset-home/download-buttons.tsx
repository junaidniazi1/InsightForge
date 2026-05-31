"use client";

import { useState } from "react";
import { downloadAuthed } from "@/lib/download";
import { Button } from "@/components/ui/button";

interface Props {
  datasetId: string;
  versionId?: string;
  label?: string;
  variant?: "primary" | "secondary";
}

export function DownloadButtons({
  datasetId,
  versionId,
  label,
  variant = "primary",
}: Props) {
  const [busy, setBusy] = useState<"csv" | "xlsx" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function go(fmt: "csv" | "xlsx") {
    setBusy(fmt);
    setError(null);
    try {
      const q = new URLSearchParams({ format: fmt });
      if (versionId) q.set("version_id", versionId);
      await downloadAuthed(
        `/datasets/${datasetId}/download?${q.toString()}`,
        `dataset.${fmt}`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="flex gap-2">
        <Button
          variant={variant === "primary" ? "primary" : "secondary"}
          onClick={() => void go("csv")}
          disabled={!!busy}
        >
          {busy === "csv" ? "Preparing CSV…" : `${label ? `${label} ` : ""}CSV`}
        </Button>
        <Button
          variant="secondary"
          onClick={() => void go("xlsx")}
          disabled={!!busy}
        >
          {busy === "xlsx" ? "Preparing Excel…" : `${label ? `${label} ` : ""}Excel`}
        </Button>
      </div>
      {error && <span className="text-xs text-[var(--color-danger)]">{error}</span>}
    </div>
  );
}

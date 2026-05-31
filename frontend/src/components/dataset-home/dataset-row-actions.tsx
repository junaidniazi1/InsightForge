"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { DeleteDatasetDialog, type DeleteSummary } from "./delete-dialog";

interface Props {
  datasetId: string;
  datasetName: string;
}

/**
 * The 🗑 trigger that sits next to a dataset row. Opens the typed-confirmation
 * dialog. On successful delete, re-runs the server-component query that
 * built the list so the row disappears.
 */
export function DatasetRowActions({ datasetId, datasetName }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  function onDeleted(summary: DeleteSummary) {
    setOpen(false);
    const f = summary.deleted.rows_by_table;
    setConfirmation(
      `Deleted “${datasetName}”. ` +
        `${summary.deleted.storage_files} file(s), ` +
        `${f.dataset_versions} version(s), ` +
        `${f.dashboards} dashboard(s), ` +
        `${f.charts} chart(s), ` +
        `${f.ai_conversations} AI message(s).`
    );
    // Re-run the parent server component so the row disappears.
    router.refresh();
    // Auto-dismiss the toast after a few seconds.
    setTimeout(() => setConfirmation(null), 6000);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Delete ${datasetName}`}
        title="Delete dataset (permanent)"
        className="rounded border border-[var(--color-danger)]/40 px-2 py-1 text-xs text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10"
      >
        🗑
      </button>
      <DeleteDatasetDialog
        dataset={{ id: datasetId, name: datasetName }}
        open={open}
        onClose={() => setOpen(false)}
        onDeleted={onDeleted}
      />
      {confirmation && (
        <div className="fixed bottom-6 right-6 z-40 max-w-md rounded-lg border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 px-4 py-3 text-sm text-[var(--color-success)] shadow-lg">
          {confirmation}
        </div>
      )}
    </>
  );
}

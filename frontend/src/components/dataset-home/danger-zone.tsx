"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DeleteDatasetDialog, type DeleteSummary } from "./delete-dialog";

interface Props {
  datasetId: string;
  datasetName: string;
}

/**
 * "Danger zone" panel pinned to the bottom of the dataset home. Same dialog as
 * the row-level delete, but visually de-emphasised so the user has to scroll
 * past everything else to find it.
 */
export function DangerZone({ datasetId, datasetName }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  function onDeleted(summary: DeleteSummary) {
    // After delete, send the user back to /sources rather than leaving them on
    // a now-404 page. The Sources page will re-query and the row will be gone.
    setOpen(false);
    void summary;
    router.push("/sources");
    router.refresh();
  }

  return (
    <>
      <Card className="border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5">
        <header className="mb-3">
          <h2 className="text-sm font-medium text-[var(--color-danger)]">Danger zone</h2>
          <p className="mt-0.5 text-xs text-[var(--color-muted)]">
            Permanently delete this dataset and everything tied to it — raw + cleaned
            files, the profile, AI cache, dashboards, and conversation history.
          </p>
        </header>
        <Button variant="danger" onClick={() => setOpen(true)}>
          Delete this dataset
        </Button>
      </Card>
      <DeleteDatasetDialog
        dataset={{ id: datasetId, name: datasetName }}
        open={open}
        onClose={() => setOpen(false)}
        onDeleted={onDeleted}
      />
    </>
  );
}

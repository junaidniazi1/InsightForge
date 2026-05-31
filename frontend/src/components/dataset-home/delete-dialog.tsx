"use client";

import { useEffect, useState } from "react";
import { apiDelete, apiGet } from "@/lib/api";
import type { Dataset } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";

interface Props {
  dataset: Pick<Dataset, "id" | "name">;
  open: boolean;
  onClose: () => void;
  /** Called after a successful delete. Receives the backend's summary. */
  onDeleted: (summary: DeleteSummary) => void;
}

export interface DeleteSummary {
  ok: true;
  deleted: {
    dataset_id: string;
    dataset_name: string | null;
    storage_files: number;
    storage_missing: number;
    rows_by_table: Record<string, number>;
  };
}

interface PreviewCounts {
  versions: number;
  dashboards: number;
  conversations: number;
}

/**
 * Confirmation dialog for permanent dataset deletion. Requires the user to
 * type the dataset's exact name before the delete button enables — typed
 * confirmation is harder to misclick than a single checkbox.
 */
export function DeleteDatasetDialog({ dataset, open, onClose, onDeleted }: Props) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewCounts | null>(null);

  // When the dialog opens, fetch lightweight counts so the user sees the
  // blast-radius before they delete. Failures here are non-fatal — the
  // delete itself returns the authoritative numbers.
  useEffect(() => {
    if (!open) return;
    setTyped("");
    setError(null);
    setPreview(null);
    (async () => {
      try {
        // Single ping that tells us version count via the profile envelope's
        // version handling; if it fails we just don't show the preview.
        // Phase 4's chart-suggestions resolves "latest version" cheaply.
        const env = await apiGet<{ version_label: string }>(
          `/datasets/${dataset.id}/chart-suggestions`
        ).catch(() => null);
        // We don't actually need the env beyond detecting reachability — the
        // real number we show below is "this dataset and everything tied to
        // it"; precise counts come from the DELETE response.
        if (env) {
          setPreview({
            versions: env.version_label === "cleaned" ? 2 : 1,  // raw + maybe cleaned
            dashboards: 0,  // backend doesn't expose this cheaply; the
            conversations: 0,  // confirmation copy below uses generic language.
          });
        }
      } catch {
        // ignore
      }
    })();
  }, [open, dataset.id]);

  // Visibility is now owned by the Modal primitive — it handles `open === false`
  // (returns null + restores focus). We just compute the confirm gate.
  const confirmed = typed.trim() === dataset.name.trim();

  async function onConfirm() {
    setBusy(true);
    setError(null);
    try {
      // apiDelete returns void, but the backend gives us the deletion summary
      // — fetch with a manual call so we can read it.
      const summary = await deleteAndRead(dataset.id);
      onDeleted(summary);
    } catch (e) {
      setError(parseError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onClose}
      dismissable={!busy}
      destructive
      size="md"
      title={
        <span className="flex flex-col">
          <span className="text-xs font-medium uppercase tracking-wide text-[var(--color-danger)]">
            Delete dataset
          </span>
          <span className="mt-1 text-lg font-semibold text-[var(--color-fg)]">
            {dataset.name}
          </span>
        </span>
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={!confirmed}
            loading={busy}
          >
            {busy ? "Deleting" : "Delete forever"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p>This permanently removes:</p>
        <ul className="list-inside list-disc space-y-1 text-xs text-[var(--color-muted)]">
          <li>the raw file and every cleaned version (in Supabase Storage)</li>
          <li>the data-health profile and AI-cached summary / story / insights</li>
          <li>every dashboard built on this dataset (charts, layout)</li>
          <li>your Ask-Your-Data conversation history for it</li>
        </ul>
        <p className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-2 text-xs text-[var(--color-danger)]">
          This action cannot be undone.
        </p>
        <div>
          <label
            htmlFor="delete-confirm"
            className="mb-1 block text-xs text-[var(--color-muted)]"
          >
            Type the dataset name to confirm:{" "}
            <span className="font-mono text-[var(--color-fg)]">{dataset.name}</span>
          </label>
          <Input
            id="delete-confirm"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={dataset.name}
            autoFocus
          />
        </div>
        {error && (
          <p className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-2 text-xs text-[var(--color-danger)]">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

/** apiDelete swallows the body, but the backend returns useful counts. */
async function deleteAndRead(datasetId: string): Promise<DeleteSummary> {
  const { createSupabaseBrowserClient } = await import("@/lib/supabase/browser");
  const supabase = createSupabaseBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error("not signed in");
  const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/datasets/${datasetId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${session.access_token}` },
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`API ${r.status}: ${text}`);
  }
  return (await r.json()) as DeleteSummary;
}

function parseError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  const m = /API \d+: (.+)$/.exec(msg);
  if (!m) return msg;
  try {
    const body = JSON.parse(m[1]);
    const inner = body?.detail ?? body;
    if (inner && typeof inner === "object" && "message" in inner) return String(inner.message);
    if (typeof inner === "string") return inner;
  } catch {
    // fall through
  }
  return msg;
}

// Silence the "unused import" notice for apiDelete; we use a manual fetch above
// so we can read the response body.
void apiDelete;

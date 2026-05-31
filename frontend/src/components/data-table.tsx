"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { Button } from "./ui/button";
import type { PreviewResponse } from "@/types";

interface Props {
  datasetId: string;
  pageSize?: number;
}

function renderCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function DataTable({ datasetId, pageSize = 50 }: Props) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiGet<PreviewResponse>(`/datasets/${datasetId}/preview?page=${page}&page_size=${pageSize}`)
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, page, pageSize]);

  if (error) return <p className="text-sm text-[var(--color-danger)]">{error}</p>;
  if (!data && loading) return <p className="text-sm text-[var(--color-muted)]">Loading preview…</p>;
  if (!data) return null;

  const totalPages = data.total_rows ? Math.max(1, Math.ceil(data.total_rows / data.page_size)) : null;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border bg-[var(--color-panel)]">
        <table className="min-w-full text-sm">
          <thead className="border-b bg-[var(--color-bg)]/50">
            <tr>
              {data.columns.map((c) => (
                <th key={c} className="whitespace-nowrap px-3 py-2 text-left font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={i} className="border-b last:border-0">
                {data.columns.map((c) => (
                  <td key={c} className="whitespace-nowrap px-3 py-2 text-[var(--color-muted)]">
                    {renderCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr>
                <td
                  colSpan={data.columns.length}
                  className="px-3 py-6 text-center text-sm text-[var(--color-muted)]"
                >
                  No rows on this page.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-[var(--color-muted)]">
        <span>
          Page {data.page}
          {totalPages ? ` of ${totalPages}` : ""}
          {data.truncated && " · large file: only first 100k rows scanned"}
        </span>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            disabled={page === 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Prev
          </Button>
          <Button
            variant="secondary"
            disabled={loading || (totalPages !== null && page >= totalPages) || data.rows.length < pageSize}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}

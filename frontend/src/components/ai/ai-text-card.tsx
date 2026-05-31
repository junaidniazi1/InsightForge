"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import type { AISummaryResponse } from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SkeletonParagraph } from "@/components/ui/skeleton";
import { AIError } from "./ai-error";

interface Props {
  datasetId: string;
  endpoint: "summary" | "story";
  title: string;
  description: string;
}

export function AITextCard({ datasetId, endpoint, title, description }: Props) {
  const [data, setData] = useState<AISummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const r = await apiGet<AISummaryResponse>(
        `/datasets/${datasetId}/ai/${endpoint}${refresh ? "?refresh=true" : ""}`
      );
      setData(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, endpoint]);

  return (
    <Card>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">{title}</h2>
          <p className="text-xs text-[var(--color-muted)]">{description}</p>
        </div>
        <Button
          variant="secondary"
          onClick={() => void load(true)}
          disabled={loading}
          className="text-xs"
        >
          {loading ? "…" : "Regenerate"}
        </Button>
      </header>
      {error ? (
        <AIError error={error} onRetry={() => void load()} />
      ) : loading && !data ? (
        <SkeletonParagraph lines={5} />
      ) : data ? (
        <>
          <div className="space-y-3 text-sm leading-relaxed">
            {(data.text || "").split(/\n{2,}/).map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </div>
          <p className="mt-4 text-[10px] text-[var(--color-muted)]">
            {data.cached ? "Cached" : "Fresh"}
            {data.created_at && ` · ${new Date(data.created_at).toLocaleString()}`}
          </p>
        </>
      ) : null}
    </Card>
  );
}

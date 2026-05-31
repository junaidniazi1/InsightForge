"use client";

import { useState } from "react";
import Link from "next/link";
import { AITextCard } from "./ai-text-card";
import { AskBox } from "./ask-box";
import { InsightsPanel } from "./insights-panel";

interface Props {
  datasetId: string;
}

export function AIPage({ datasetId }: Props) {
  const [seedQuestion, setSeedQuestion] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel)]/60 p-3 text-xs text-[var(--color-muted)]">
        <strong className="font-medium text-[var(--color-fg)]">Privacy:</strong>{" "}
        AI runs on the version your dashboard uses (latest cleaned, else raw).
        Only the schema, semantic types, and aggregate statistics are sent to
        the model — never your raw data rows.{" "}
        <Link
          href={`/sources/${datasetId}/dashboard`}
          className="text-[var(--color-accent)] hover:underline"
        >
          See provenance on the dashboard
        </Link>
        .
      </div>

      <AITextCard
        datasetId={datasetId}
        endpoint="summary"
        title="Summary"
        description="What the dataset contains and its overall quality."
      />

      <AITextCard
        datasetId={datasetId}
        endpoint="story"
        title="Data story"
        description="The key findings as a short narrative for a non-technical reader."
      />

      <InsightsPanel
        datasetId={datasetId}
        onAskSuggested={(q) => setSeedQuestion(q)}
      />

      <AskBox
        datasetId={datasetId}
        initialQuestion={seedQuestion}
        onConsumeInitial={() => setSeedQuestion(null)}
      />
    </div>
  );
}

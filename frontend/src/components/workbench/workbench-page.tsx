"use client";

import { useEffect, useMemo, useState } from "react";
import { clsx } from "clsx";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { Profile, ProfileEnvelope } from "@/types";
import { Card } from "@/components/ui/card";
import { AnomalyTab } from "./anomaly-tab";
import { ClusteringTab } from "./clustering-tab";
import { CorrelationTab } from "./correlation-tab";
import { FeatureImportanceTab } from "./feature-importance-tab";
import { HypothesisTab } from "./hypothesis-tab";
import { ModelingTab } from "./modeling-tab";
import { PCATab } from "./pca-tab";
import { StatsTab } from "./stats-tab";
import { TimeseriesTab } from "./timeseries-tab";

interface Props {
  datasetId: string;
}

interface TabDef {
  key: TabKey;
  label: string;
  description: string;
  // Phase 7B tabs are added in the next checkpoint.
  comingSoon?: boolean;
}

type TabKey =
  | "stats"
  | "correlation"
  | "hypothesis"
  | "timeseries"
  | "clustering"
  | "pca"
  | "anomaly"
  | "feature_importance"
  | "modeling";

const TABS: TabDef[] = [
  { key: "stats", label: "Statistics", description: "Descriptive deep-dive per column." },
  { key: "correlation", label: "Correlation", description: "Pearson / Spearman / Kendall." },
  { key: "hypothesis", label: "Hypothesis", description: "t-test, ANOVA, χ², Mann-Whitney." },
  { key: "timeseries", label: "Time-series", description: "Resample, decompose, ACF/PACF, ADF." },
  { key: "clustering", label: "Clustering", description: "KMeans with auto-k + PCA scatter." },
  { key: "pca", label: "PCA", description: "Scree + projection + loadings." },
  { key: "anomaly", label: "Anomaly", description: "Isolation Forest with PCA scatter." },
  { key: "feature_importance", label: "Feature importance", description: "Random Forest + OOB score." },
  { key: "modeling", label: "Modeling", description: "Baselines + predictions CSV." },
];

export function WorkbenchPage({ datasetId }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("stats");

  useEffect(() => {
    apiGet<ProfileEnvelope>(`/datasets/${datasetId}/profile`)
      .then((env) => {
        if (env.profile) setProfile(env.profile);
        else setError("Profile a dataset version first (open Data Health).");
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [datasetId]);

  const columns = useMemo(() => profile?.columns ?? [], [profile]);
  const hasDatetime = columns.some((c) => c.semantic_type === "datetime");
  const hasNumeric = columns.some((c) => c.semantic_type === "numeric");

  if (error) {
    return (
      <Card>
        <p className="text-sm text-[var(--color-danger)]">{error}</p>
        <p className="mt-2 text-xs text-[var(--color-muted)]">
          Open{" "}
          <Link href={`/sources/${datasetId}/health`} className="text-[var(--color-accent)] hover:underline">
            Data Health
          </Link>{" "}
          to profile the dataset.
        </p>
      </Card>
    );
  }
  if (!profile) {
    return <p className="text-sm text-[var(--color-muted)]">Loading profile…</p>;
  }

  function isDisabled(key: TabKey): boolean {
    const numericCount = columns.filter((c) => c.semantic_type === "numeric").length;
    if (key === "timeseries") return !(hasDatetime && hasNumeric);
    if (key === "stats") return !hasNumeric;
    if (
      key === "correlation" ||
      key === "clustering" ||
      key === "pca" ||
      key === "anomaly"
    ) {
      return numericCount < 2;
    }
    if (key === "feature_importance" || key === "modeling") {
      // Need at least one viable target column (anything goes — backend decides
      // regression vs classification) AND at least one usable feature.
      return columns.length < 2;
    }
    return false;
  }

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <nav className="flex flex-wrap gap-1 border-b">
        {TABS.map((t) => {
          const disabled = t.comingSoon || isDisabled(t.key);
          return (
            <button
              key={t.key}
              type="button"
              disabled={disabled}
              onClick={() => setTab(t.key)}
              className={clsx(
                "rounded-t-md border-b-2 px-3 py-2 text-xs transition-colors",
                tab === t.key
                  ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                  : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-fg)]",
                disabled && "cursor-not-allowed opacity-40"
              )}
              title={t.comingSoon ? "Ships in 7B" : disabled ? "Not applicable to this dataset" : t.description}
            >
              {t.label}
              {t.comingSoon && <span className="ml-1 text-[10px]">· 7B</span>}
            </button>
          );
        })}
      </nav>

      {/* Active tab */}
      {tab === "stats" && <StatsTab datasetId={datasetId} columns={columns} />}
      {tab === "correlation" && <CorrelationTab datasetId={datasetId} columns={columns} />}
      {tab === "hypothesis" && <HypothesisTab datasetId={datasetId} columns={columns} />}
      {tab === "timeseries" && <TimeseriesTab datasetId={datasetId} columns={columns} />}
      {tab === "clustering" && <ClusteringTab datasetId={datasetId} columns={columns} />}
      {tab === "pca" && <PCATab datasetId={datasetId} columns={columns} />}
      {tab === "anomaly" && <AnomalyTab datasetId={datasetId} columns={columns} />}
      {tab === "feature_importance" && <FeatureImportanceTab datasetId={datasetId} columns={columns} />}
      {tab === "modeling" && <ModelingTab datasetId={datasetId} columns={columns} />}
    </div>
  );
}

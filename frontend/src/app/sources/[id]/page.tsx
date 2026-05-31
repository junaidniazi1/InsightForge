import { notFound } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { CapabilityCards } from "@/components/dataset-home/capability-cards";
import { DangerZone } from "@/components/dataset-home/danger-zone";
import { DownloadButtons } from "@/components/dataset-home/download-buttons";
import { DataTable } from "@/components/data-table";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import type { Dataset } from "@/types";

export const dynamic = "force-dynamic";

interface DatasetVersionRow {
  id: string;
  label: "raw" | "cleaned";
  version_no: number;
  cleaning_steps: unknown[] | null;
  created_at: string;
}

export default async function DatasetHomePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createSupabaseServerClient();

  const [{ data, error }, versionsRes] = await Promise.all([
    supabase
      .from("datasets")
      .select(
        "id,user_id,name,source_type,storage_path,row_count,column_count,status,created_at"
      )
      .eq("id", id)
      .maybeSingle(),
    supabase
      .from("dataset_versions")
      .select("id,label,version_no,cleaning_steps,created_at")
      .eq("dataset_id", id)
      .order("version_no", { ascending: false }),
  ]);
  if (error || !data) return notFound();
  const ds = data as Dataset;
  const versions = (versionsRes.data as DatasetVersionRow[] | null) ?? [];
  const cleaned = versions.find((v) => v.label === "cleaned");
  const raw = versions.find((v) => v.label === "raw");
  const stepCount = Array.isArray(cleaned?.cleaning_steps)
    ? cleaned!.cleaning_steps.length
    : 0;

  const sourceLabel =
    ds.source_type === "file_csv"
      ? "CSV"
      : ds.source_type === "file_excel"
        ? "Excel"
        : "DB connection";

  return (
    <div className="space-y-8">
      <PageHeader
        title={ds.name}
        back={{ label: "Sources", href: "/sources" }}
        description={
          `${sourceLabel} · uploaded ${new Date(ds.created_at).toLocaleString()} · status ${ds.status}` +
          (ds.row_count !== null
            ? ` · ${ds.row_count.toLocaleString()} rows × ${ds.column_count} cols`
            : "")
        }
      />

      {/* ---- Standalone download (for cleaning-only users) ---- */}
      {cleaned && (
        <Card className="border-[var(--color-success)]/30 bg-[var(--color-success)]/5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-medium text-[var(--color-success)]">
                Cleaned data ready
              </h2>
              <p className="text-xs text-[var(--color-muted)]">
                v{cleaned.version_no} · {stepCount} preprocessing step{stepCount === 1 ? "" : "s"} ·{" "}
                created {new Date(cleaned.created_at).toLocaleString()}
              </p>
            </div>
            <DownloadButtons
              datasetId={ds.id}
              versionId={cleaned.id}
              label="Download"
            />
          </div>
        </Card>
      )}

      {/* ---- Capability cards ---- */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-[var(--color-muted)]">
          What would you like to do?
        </h2>
        <CapabilityCards
          dataset={ds}
          hasCleanedVersion={!!cleaned}
          cleanedStepCount={stepCount}
        />
      </section>

      {/* ---- Raw download (always available) ---- */}
      {raw && (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-medium">Raw upload</h2>
              <p className="text-xs text-[var(--color-muted)]">
                Original file as you uploaded it. Unmodified.
              </p>
            </div>
            <DownloadButtons
              datasetId={ds.id}
              versionId={raw.id}
              label="Download raw"
              variant="secondary"
            />
          </div>
        </Card>
      )}

      {/* ---- Preview ---- */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-[var(--color-muted)]">Preview</h2>
        <DataTable datasetId={ds.id} />
      </section>

      {/* ---- Danger zone (pinned to the bottom; reachable but unobtrusive) ---- */}
      <DangerZone datasetId={ds.id} datasetName={ds.name} />
    </div>
  );
}

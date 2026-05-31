import { notFound } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { WorkbenchPage } from "@/components/workbench/workbench-page";
import { PageHeader } from "@/components/ui/page-header";
import type { Dataset } from "@/types";

export const dynamic = "force-dynamic";

export default async function WorkbenchRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("datasets")
    .select(
      "id,user_id,name,source_type,storage_path,row_count,column_count,status,created_at",
    )
    .eq("id", id)
    .maybeSingle();
  if (error || !data) return notFound();
  const ds = data as Dataset;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Analyst Workbench · ${ds.name}`}
        back={{ label: ds.name, href: `/sources/${ds.id}` }}
        description="Statistics, hypothesis tests, time-series, and ML. Every tool runs on the latest cleaned version (or raw if no cleaned exists)."
      />
      <WorkbenchPage datasetId={ds.id} />
    </div>
  );
}

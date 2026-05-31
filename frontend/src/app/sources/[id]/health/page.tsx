import { notFound } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { HealthReport } from "@/components/health/health-report";
import { PageHeader } from "@/components/ui/page-header";
import type { Dataset } from "@/types";

export const dynamic = "force-dynamic";

export default async function DataHealthPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("datasets")
    .select("id,user_id,name,source_type,storage_path,row_count,column_count,status,created_at")
    .eq("id", id)
    .maybeSingle();
  if (error || !data) return notFound();
  const ds = data as Dataset;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Data Health · ${ds.name}`}
        back={{ label: ds.name, href: `/sources/${ds.id}` }}
        description="Per-column statistics, detected issues, and suggested fixes. Pick what you want, then Review & clean."
      />
      <HealthReport datasetId={ds.id} />
    </div>
  );
}

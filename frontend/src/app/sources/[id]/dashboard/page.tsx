import { notFound } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { DashboardBuilder } from "@/components/dashboard/dashboard-builder";
import { PageHeader } from "@/components/ui/page-header";
import type { Dataset } from "@/types";

export const dynamic = "force-dynamic";

export default async function DashboardRoute({
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
        title={`Dashboard · ${ds.name}`}
        back={{ label: ds.name, href: `/sources/${ds.id}` }}
        description="Auto-suggested charts with KPI cards and global filters. Drag corners to resize tiles; drag the chart header to reposition."
      />
      <DashboardBuilder datasetId={ds.id} datasetName={ds.name} />
    </div>
  );
}

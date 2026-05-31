import { notFound } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { CleanPage } from "@/components/clean/clean-page";
import { PageHeader } from "@/components/ui/page-header";
import type { Dataset } from "@/types";

export const dynamic = "force-dynamic";

export default async function CleanRoute({
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
        title={`Clean · ${ds.name}`}
        back={{ label: ds.name, href: `/sources/${ds.id}` }}
        description="Build an ordered pipeline of cleaning steps and apply it. The raw upload is never modified — this produces a new cleaned version."
      />
      <CleanPage datasetId={ds.id} />
    </div>
  );
}

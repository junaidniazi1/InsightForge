import Link from "next/link";
import { Database, FileUp } from "lucide-react";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { UploadZone } from "@/components/upload-zone";
import { DatasetsList } from "@/components/dataset-home/datasets-list";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import type { Dataset } from "@/types";

export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("datasets")
    .select(
      "id,user_id,name,source_type,storage_path,row_count,column_count,status,created_at",
    )
    .order("created_at", { ascending: false });

  const datasets = (data as Dataset[] | null) ?? [];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Sources"
        description="Upload a CSV or Excel file, or connect a live database."
      />

      <div className="grid gap-4 md:grid-cols-2">
        <UploadZone />

        <Card className="flex flex-col items-center justify-center border-dashed text-center">
          <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
            <Database className="h-5 w-5" />
          </div>
          <h3 className="text-base font-medium">Connect a database</h3>
          <p className="mt-1 max-w-xs text-sm text-[var(--color-muted)]">
            Pull tables (or a read-only query) from Postgres, MySQL, or SQLite.
          </p>
          <Link
            href="/connections"
            className="mt-5 inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[var(--color-accent-strong)]"
          >
            <FileUp className="h-4 w-4" />
            Connect a database
          </Link>
        </Card>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-medium">Your datasets</h2>
        {error ? (
          <Card>
            <p className="text-sm text-[var(--color-danger)]">
              Couldn’t load datasets: {error.message}
            </p>
          </Card>
        ) : (
          <DatasetsList datasets={datasets} />
        )}
      </section>
    </div>
  );
}

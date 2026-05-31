"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { Button } from "./ui/button";
import type { SourceType } from "@/types";

const ACCEPT = ".csv,.xlsx,.xls";
const MAX_BYTES = 200 * 1024 * 1024; // 200 MB

function sourceTypeOf(name: string): SourceType | null {
  const lower = name.toLowerCase();
  if (lower.endsWith(".csv")) return "file_csv";
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) return "file_excel";
  return null;
}

export function UploadZone() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string>("");

  async function handleFile(file: File) {
    setError(null);
    const source_type = sourceTypeOf(file.name);
    if (!source_type) {
      setError("Unsupported file. Upload CSV or Excel.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(`File too large (${Math.round(file.size / 1024 / 1024)} MB). Max is 200 MB.`);
      return;
    }

    setBusy(true);
    try {
      const supabase = createSupabaseBrowserClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error("not signed in");

      setProgress("Uploading to storage...");
      const objectPath = `${user.id}/${crypto.randomUUID()}-${file.name}`;
      const { error: upErr } = await supabase.storage
        .from("datasets")
        .upload(objectPath, file, { contentType: file.type || undefined, upsert: false });
      if (upErr) throw upErr;

      setProgress("Registering dataset...");
      const { data: ds, error: insErr } = await supabase
        .from("datasets")
        .insert({
          user_id: user.id,
          name: file.name,
          source_type,
          storage_path: objectPath,
          status: "uploaded",
        })
        .select("id")
        .single();
      if (insErr) throw insErr;

      router.push(`/sources/${ds.id}`);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      setProgress("");
    }
  }

  return (
    <div className="rounded-lg border-2 border-dashed border-[var(--color-border)] bg-[var(--color-panel)] p-10 text-center">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleFile(f);
        }}
      />
      <p className="mb-1 text-lg font-medium">Upload a dataset</p>
      <p className="mb-4 text-sm text-[var(--color-muted)]">CSV or Excel, up to 200 MB.</p>
      <Button onClick={() => inputRef.current?.click()} disabled={busy}>
        {busy ? progress || "Working..." : "Choose file"}
      </Button>
      {error && <p className="mt-4 text-sm text-[var(--color-danger)]">{error}</p>}
    </div>
  );
}

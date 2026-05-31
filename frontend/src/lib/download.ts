"use client";

import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

async function authHeader(): Promise<HeadersInit> {
  const supabase = createSupabaseBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error("not signed in");
  return { Authorization: `Bearer ${session.access_token}` };
}

/**
 * Download an authenticated endpoint as a file. The browser can't put an
 * Authorization header on a plain <a href>, so we fetch the blob, then trigger
 * the download client-side.
 */
export async function downloadAuthed(path: string, suggestedName: string): Promise<void> {
  const headers = await authHeader();
  const r = await fetch(`${API_URL}${path}`, { headers, cache: "no-store" });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`Download failed (${r.status}): ${text || r.statusText}`);
  }
  // Prefer the server's filename if present.
  const disposition = r.headers.get("content-disposition") || "";
  const m = /filename="?([^";]+)"?/.exec(disposition);
  const name = m?.[1] || suggestedName;

  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

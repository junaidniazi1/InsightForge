"use client";

import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

async function authHeader(): Promise<HeadersInit> {
  const supabase = createSupabaseBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error("not signed in");
  return { Authorization: `Bearer ${session.access_token}` };
}

export async function apiGet<T>(path: string): Promise<T> {
  const headers = await authHeader();
  const r = await fetch(`${API_URL}${path}`, { headers, cache: "no-store" });
  if (!r.ok) {
    const body = await r.text();
    throw new Error(`API ${r.status}: ${body}`);
  }
  return (await r.json()) as T;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const headers = await authHeader();
  const r = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`API ${r.status}: ${text}`);
  }
  return (await r.json()) as T;
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const headers = await authHeader();
  const r = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers: { ...headers, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`API ${r.status}: ${text}`);
  }
  return (await r.json()) as T;
}

export async function apiDelete(path: string): Promise<void> {
  const headers = await authHeader();
  const r = await fetch(`${API_URL}${path}`, {
    method: "DELETE",
    headers,
    cache: "no-store",
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`API ${r.status}: ${text}`);
  }
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { DbConnectionDetail, ColumnInfo, ImportResponse } from "@/types";

export default function ConnectionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const connId = params.id as string;

  const [conn, setConn] = useState<DbConnectionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [mode, setMode] = useState<"table" | "query">("table");
  const [selectedTable, setSelectedTable] = useState("");
  const [sql, setSql] = useState("");
  const [limit, setLimit] = useState<number | "">("");
  const [datasetName, setDatasetName] = useState("");
  
  const [columns, setColumns] = useState<ColumnInfo[]>([]);
  const [loadingCols, setLoadingCols] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  useEffect(() => {
    fetchConnection();
  }, [connId]);

  async function fetchConnection() {
    setLoading(true);
    try {
      const res = await fetch(`/api/proxy/db-connections/${connId}`);
      if (!res.ok) throw new Error("Failed to load connection");
      const data = await res.json();
      setConn(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (mode === "table" && selectedTable) {
      fetchColumns(selectedTable);
    } else {
      setColumns([]);
    }
  }, [mode, selectedTable]);

  async function fetchColumns(tableName: string) {
    setLoadingCols(true);
    try {
      const res = await fetch(`/api/proxy/db-connections/${connId}/describe?table=${encodeURIComponent(tableName)}`);
      if (res.ok) {
        const data = await res.json();
        setColumns(data.columns || []);
      }
    } catch (err) {
      // Ignore
    } finally {
      setLoadingCols(false);
    }
  }

  async function handleImport(e: React.FormEvent) {
    e.preventDefault();
    setIsImporting(true);
    
    try {
      const payload: any = {
        mode,
        name: datasetName || undefined,
        row_limit: limit === "" ? undefined : Number(limit),
      };
      
      if (mode === "table") {
        if (!selectedTable) throw new Error("Please select a table");
        payload.table = selectedTable;
      } else {
        if (!sql.trim()) throw new Error("Please enter a SQL query");
        payload.sql = sql;
      }

      const res = await fetch(`/api/proxy/db-connections/${connId}/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Import failed");
      }
      
      const data: ImportResponse = await res.json();
      
      // Redirect to the new dataset's source page
      router.push(`/sources/${data.dataset_id}`);
    } catch (err: any) {
      alert(err.message);
      setIsImporting(false);
    }
  }

  if (loading) return <div className="p-8 text-center">Loading...</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error}</div>;
  if (!conn) return null;

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <header className="flex items-center justify-between border-b pb-4">
        <div>
          <Link
            href="/connections"
            className="text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
          >
            ← Back to Connections
          </Link>
          <h1 className="mt-2 text-2xl font-semibold">{conn.name}</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {conn.db_type} · {conn.host || "local"} · {conn.database}
          </p>
        </div>
      </header>

      <div className="grid gap-8 md:grid-cols-2">
        {/* Wizard Form */}
        <div className="rounded-lg border bg-[var(--color-panel)] p-6">
          <h2 className="text-lg font-medium mb-4">Import Wizard</h2>
          <form onSubmit={handleImport} className="space-y-5">
            <div>
              <label className="mb-1 block text-sm font-medium">Import Mode</label>
              <div className="flex rounded border overflow-hidden">
                <button
                  type="button"
                  onClick={() => setMode("table")}
                  className={`flex-1 py-2 text-sm font-medium ${mode === "table" ? "bg-[var(--color-accent)] text-white" : "hover:bg-[var(--color-border)]"}`}
                >
                  Entire Table
                </button>
                <button
                  type="button"
                  onClick={() => setMode("query")}
                  className={`flex-1 py-2 text-sm font-medium border-l ${mode === "query" ? "bg-[var(--color-accent)] text-white" : "hover:bg-[var(--color-border)]"}`}
                >
                  Custom Query
                </button>
              </div>
            </div>

            {mode === "table" ? (
              <div>
                <label className="mb-1 block text-sm font-medium">Select Table or View</label>
                <select
                  required
                  value={selectedTable}
                  onChange={(e) => setSelectedTable(e.target.value)}
                  className="w-full rounded border px-3 py-2 text-sm bg-transparent"
                >
                  <option value="">-- Choose --</option>
                  {conn.tables.map((t) => (
                    <option key={`${t.schema || ""}-${t.name}`} value={t.name}>
                      {t.schema ? `${t.schema}.${t.name}` : t.name} ({t.type})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div>
                <label className="mb-1 block text-sm font-medium">Read-Only SQL Query</label>
                <textarea
                  required
                  value={sql}
                  onChange={(e) => setSql(e.target.value)}
                  rows={6}
                  className="w-full rounded border px-3 py-2 text-sm bg-transparent font-mono"
                  placeholder="SELECT * FROM users WHERE active = true"
                />
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  Only SELECT or WITH statements allowed. No destructive commands.
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Row Limit (Optional)</label>
                <input
                  type="number"
                  min="1"
                  value={limit}
                  onChange={(e) => setLimit(e.target.value ? Number(e.target.value) : "")}
                  className="w-full rounded border px-3 py-2 text-sm bg-transparent"
                  placeholder="e.g. 100000"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Dataset Name (Optional)</label>
                <input
                  type="text"
                  value={datasetName}
                  onChange={(e) => setDatasetName(e.target.value)}
                  className="w-full rounded border px-3 py-2 text-sm bg-transparent"
                  placeholder="Auto-generated if blank"
                />
              </div>
            </div>

            <div className="pt-4">
              <button
                type="submit"
                disabled={isImporting || (mode === "table" ? !selectedTable : !sql)}
                className="w-full rounded bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent)]/90 disabled:opacity-50"
              >
                {isImporting ? "Importing..." : "Import Data"}
              </button>
            </div>
          </form>
        </div>

        {/* Schema Preview */}
        <div>
          <h2 className="text-lg font-medium mb-4">Schema Preview</h2>
          {mode === "table" ? (
            !selectedTable ? (
              <div className="rounded-lg border border-dashed p-8 text-center text-sm text-[var(--color-muted)]">
                Select a table to see its columns.
              </div>
            ) : loadingCols ? (
              <p className="text-sm text-[var(--color-muted)]">Fetching schema...</p>
            ) : columns.length === 0 ? (
              <p className="text-sm text-[var(--color-muted)]">No columns found.</p>
            ) : (
              <div className="rounded-lg border overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead className="bg-[var(--color-panel)] text-[var(--color-muted)] border-b">
                    <tr>
                      <th className="px-4 py-2 font-medium">Column Name</th>
                      <th className="px-4 py-2 font-medium">Type</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
                    {columns.map((col) => (
                      <tr key={col.name}>
                        <td className="px-4 py-2 font-mono">{col.name}</td>
                        <td className="px-4 py-2 text-[var(--color-muted)]">{col.type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            <div className="rounded-lg border border-dashed p-8 text-center text-sm text-[var(--color-muted)]">
              Write a SQL query to extract specific data. The result schema will depend on your query.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

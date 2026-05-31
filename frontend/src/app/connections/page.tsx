"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Database, FlaskConical, Plug, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { SkeletonLine } from "@/components/ui/skeleton";
import type { DbConnection } from "@/types";

const DRIVER_LABEL: Record<string, string> = {
  postgres: "PostgreSQL",
  mysql: "MySQL",
  sqlite: "SQLite",
};

const DRIVER_ICON: Record<string, string> = {
  postgres: "🐘",
  mysql: "🐬",
  sqlite: "💾",
};

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<DbConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [name, setName] = useState("");
  const [dbType, setDbType] = useState<"postgres" | "mysql" | "sqlite">("postgres");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(5432);
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    fetchConnections();
  }, []);

  async function fetchConnections() {
    setLoading(true);
    try {
      const res = await fetch("/api/proxy/db-connections");
      if (!res.ok) throw new Error("Failed to load connections");
      const data = await res.json();
      setConnections(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this connection? Saved credentials will be removed.")) return;
    try {
      await fetch(`/api/proxy/db-connections/${id}`, { method: "DELETE" });
      setConnections((prev) => prev.filter((c) => c.id !== id));
    } catch {
      alert("Failed to delete connection.");
    }
  }

  async function handleTest() {
    setIsTesting(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/proxy/db-connections/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ db_type: dbType, host, port, database, username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setTestResult({ success: false, message: data.detail || "Connection failed" });
      } else {
        setTestResult(data);
      }
    } catch (err) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsTesting(false);
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    try {
      const res = await fetch("/api/proxy/db-connections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, db_type: dbType, host, port, database, username, password }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save connection");
      }
      const newConn = await res.json();
      setConnections([newConn, ...connections]);
      setName("");
      setHost("");
      setDatabase("");
      setUsername("");
      setPassword("");
      setTestResult(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSaving(false);
    }
  }

  const formIncomplete =
    !name || !database || (dbType !== "sqlite" && (!host || !username));

  return (
    <div className="space-y-8">
      <PageHeader
        title="Database connections"
        description="Connect Postgres, MySQL, or SQLite to import tables or read-only queries as datasets."
        back={{ label: "Sources", href: "/sources" }}
      />

      <div className="grid gap-8 md:grid-cols-2">
        {/* ----- New connection form ----- */}
        <Card>
          <div className="mb-4 flex items-center gap-2">
            <Plug className="h-4 w-4 text-[var(--color-accent)]" />
            <h2 className="text-base font-medium">New connection</h2>
          </div>
          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label htmlFor="conn-name" className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
                Connection name
              </label>
              <Input
                id="conn-name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Prod Analytics"
              />
            </div>

            <div>
              <label htmlFor="conn-type" className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
                Database type
              </label>
              <Select
                id="conn-type"
                value={dbType}
                onChange={(e) => {
                  const t = e.target.value as "postgres" | "mysql" | "sqlite";
                  setDbType(t);
                  if (t === "postgres") setPort(5432);
                  if (t === "mysql") setPort(3306);
                }}
              >
                <option value="postgres">🐘 PostgreSQL</option>
                <option value="mysql">🐬 MySQL</option>
                <option value="sqlite">💾 SQLite</option>
              </Select>
            </div>

            {dbType !== "sqlite" && (
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label htmlFor="conn-host" className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
                    Host
                  </label>
                  <Input
                    id="conn-host"
                    required
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                    placeholder="db.example.com"
                  />
                </div>
                <div>
                  <label htmlFor="conn-port" className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
                    Port
                  </label>
                  <Input
                    id="conn-port"
                    required
                    type="number"
                    value={port}
                    onChange={(e) => setPort(Number(e.target.value))}
                  />
                </div>
              </div>
            )}

            <div>
              <label htmlFor="conn-db" className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
                {dbType === "sqlite" ? "File path (server-local)" : "Database name"}
              </label>
              <Input
                id="conn-db"
                required
                value={database}
                onChange={(e) => setDatabase(e.target.value)}
                placeholder={dbType === "sqlite" ? "/path/to/db.sqlite3" : "analytics_db"}
              />
            </div>

            {dbType !== "sqlite" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="conn-user" className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
                    Username
                  </label>
                  <Input
                    id="conn-user"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div>
                  <label htmlFor="conn-pw" className="mb-1 block text-xs font-medium text-[var(--color-muted)]">
                    Password
                  </label>
                  <Input
                    id="conn-pw"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="off"
                  />
                </div>
              </div>
            )}

            {testResult && (
              <div
                className={
                  "flex items-start gap-2 rounded-lg border p-2 text-xs " +
                  (testResult.success
                    ? "border-[var(--color-success)]/40 bg-[var(--color-success)]/10 text-[var(--color-success)]"
                    : "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 text-[var(--color-danger)]")
                }
              >
                {testResult.success ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                ) : (
                  <XCircle className="h-4 w-4 shrink-0" />
                )}
                <span>
                  {testResult.success ? "Connection successful." : testResult.message}
                </span>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={handleTest}
                loading={isTesting}
                disabled={formIncomplete && !isTesting}
                leftIcon={<FlaskConical className="h-4 w-4" />}
                className="flex-1"
              >
                Test
              </Button>
              <Button
                type="submit"
                loading={isSaving}
                disabled={!name || !database}
                className="flex-1"
              >
                Save connection
              </Button>
            </div>
          </form>
        </Card>

        {/* ----- Saved connections list ----- */}
        <div>
          <h2 className="mb-4 text-base font-medium">Saved connections</h2>
          {loading ? (
            <Card>
              <div className="space-y-3">
                <SkeletonLine height={14} width="40%" />
                <SkeletonLine height={10} width="70%" />
                <SkeletonLine height={10} width="55%" />
              </div>
            </Card>
          ) : error ? (
            <Card>
              <p className="text-sm text-[var(--color-danger)]">{error}</p>
            </Card>
          ) : connections.length === 0 ? (
            <EmptyState
              icon={<Database className="h-5 w-5" />}
              title="No saved connections"
              description="Fill in the form on the left, hit Test, then Save. Your password is encrypted before it touches the database."
            />
          ) : (
            <ul className="space-y-3">
              {connections.map((conn) => (
                <Card key={conn.id} interactive className="flex items-center justify-between p-4">
                  <Link href={`/connections/${conn.id}`} className="flex min-w-0 flex-1 items-center gap-3">
                    <span className="text-2xl" aria-hidden="true">
                      {DRIVER_ICON[conn.db_type] ?? "📦"}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-medium text-[var(--color-fg)]">
                        {conn.name}
                      </p>
                      <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                        {DRIVER_LABEL[conn.db_type] ?? conn.db_type}
                        {conn.db_type !== "sqlite" && (
                          <>
                            {" · "}
                            <span className="font-mono">{conn.host}:{conn.port}</span>
                          </>
                        )}
                      </p>
                    </div>
                  </Link>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge variant="neutral" compact>
                      {conn.db_type}
                    </Badge>
                    <Link
                      href={`/connections/${conn.id}`}
                      className="inline-flex h-8 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 text-xs font-medium transition-colors hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg)]"
                    >
                      Open
                    </Link>
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDelete(conn.id)}
                    >
                      Delete
                    </Button>
                  </div>
                </Card>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

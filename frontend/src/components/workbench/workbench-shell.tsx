"use client";

import { type ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { Chart } from "@/components/charts/chart";
import type { WorkbenchChart, WorkbenchErrorPayload } from "@/types";

interface Props {
  configPanel: ReactNode;
  running: boolean;
  error: WorkbenchErrorPayload | string | null;
  result: ReactNode;
  charts: WorkbenchChart[];
  interpretation?: string;
}

export function WorkbenchShell({
  configPanel,
  running,
  error,
  result,
  charts,
  interpretation,
}: Props) {
  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      <aside>
        <Card>{configPanel}</Card>
      </aside>
      <div className="space-y-4">
        {error && (
          <Card>
            <ErrorView error={error} />
          </Card>
        )}
        {running && !error && (
          <Card>
            <p className="text-sm text-[var(--color-muted)]">Running…</p>
          </Card>
        )}
        {!error && !running && (result || charts.length > 0 || interpretation) && (
          <>
            {interpretation && (
              <Card>
                <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                  Interpretation
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                  {interpretation}
                </p>
              </Card>
            )}
            {result && <Card>{result}</Card>}
            {charts.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2">
                {charts.map((c, i) => (
                  <ChartCard key={i} chart={c} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ChartCard({ chart }: { chart: WorkbenchChart }) {
  return (
    <Card className="overflow-hidden p-0">
      <header className="border-b px-3 py-2">
        <p className="text-xs font-medium">{chart.title}</p>
      </header>
      <div className="p-2">
        <Chart spec={chart.spec} data={chart.data} height={280} />
      </div>
    </Card>
  );
}

function ErrorView({ error }: { error: WorkbenchErrorPayload | string }) {
  if (typeof error === "string") {
    return <p className="text-sm text-[var(--color-danger)]">{error}</p>;
  }
  return (
    <div className="text-sm">
      <p className="text-[var(--color-danger)]">{error.message}</p>
      <p className="mt-1 text-[10px] font-mono text-[var(--color-muted)]">
        reason: {error.reason}
      </p>
    </div>
  );
}

export function parseWorkbenchError(raw: unknown): WorkbenchErrorPayload | string {
  const msg = raw instanceof Error ? raw.message : String(raw);
  // Our router serialises { reason, message } as the detail; api wrappers
  // re-stringify into "API 400: {json}".
  const match = /API \d+: (.+)$/.exec(msg);
  if (!match) return msg;
  try {
    const body = JSON.parse(match[1]);
    const inner = body?.detail ?? body;
    if (inner && typeof inner === "object" && "reason" in inner && "message" in inner) {
      return { reason: String(inner.reason), message: String(inner.message) };
    }
    if (typeof inner === "string") return inner;
  } catch {
    // fall through
  }
  return msg;
}

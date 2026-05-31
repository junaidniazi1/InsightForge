"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type {
  AIAskResponse,
  AIConversationResponse,
  AIConversationTurn,
  AIResultTable,
  ChartDataResponse,
  ChartSpec,
} from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Chart } from "@/components/charts/chart";
import { AIError } from "./ai-error";

interface Props {
  datasetId: string;
  /** External callers can stuff a suggested question in here. */
  initialQuestion?: string | null;
  onConsumeInitial?: () => void;
}

const SUGGESTED_PROMPTS = [
  "Which categories have the highest average value?",
  "What's the trend over time?",
  "Are any pairs of numeric columns strongly correlated?",
  "How many rows match the most common category?",
];

interface RenderedTurn {
  role: AIConversationTurn["role"];
  content: string;
  created_at: string;
  payload?: AIConversationTurn["payload"];
}

export function AskBox({ datasetId, initialQuestion, onConsumeInitial }: Props) {
  const [question, setQuestion] = useState<string>("");
  const [history, setHistory] = useState<RenderedTurn[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Initial load: conversation history.
  useEffect(() => {
    apiGet<AIConversationResponse>(`/datasets/${datasetId}/ai/conversation`)
      .then((r) => setHistory(r.turns))
      .catch(() => setHistory([]));
  }, [datasetId]);

  // Externally-suggested question (from auto-insights chip click).
  useEffect(() => {
    if (initialQuestion) {
      setQuestion(initialQuestion);
      onConsumeInitial?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  // Scroll the conversation when it grows.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [history.length, asking]);

  async function ask() {
    const q = question.trim();
    if (!q || asking) return;
    setAsking(true);
    setError(null);
    // Optimistic: append the user turn.
    const userTurn: RenderedTurn = {
      role: "user",
      content: q,
      created_at: new Date().toISOString(),
    };
    setHistory((h) => [...h, userTurn]);
    setQuestion("");
    try {
      const r = await apiPost<AIAskResponse>(`/datasets/${datasetId}/ai/ask`, {
        question: q,
      });
      const aTurn: RenderedTurn = {
        role: "assistant",
        content: r.answer,
        created_at: new Date().toISOString(),
        payload: {
          answer: r.answer,
          analysis_spec: r.analysis_spec,
          result_table: r.result_table,
          suggested_chart: r.suggested_chart,
        },
      };
      setHistory((h) => [...h, aTurn]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      // Roll back the user turn if the call failed at the precheck.
      setHistory((h) => h.slice(0, -1));
      setQuestion(q);
    } finally {
      setAsking(false);
    }
  }

  return (
    <Card>
      <header className="mb-3">
        <h2 className="text-lg font-medium">Ask Your Data</h2>
        <p className="text-xs text-[var(--color-muted)]">
          Plain English → a planned analysis you can audit, run on your data.
        </p>
      </header>

      <div
        ref={scrollRef}
        className="max-h-[480px] space-y-3 overflow-y-auto rounded border bg-[var(--color-bg)]/40 p-3"
      >
        {history.length === 0 ? (
          <div className="space-y-2 py-4 text-center text-xs text-[var(--color-muted)]">
            <p>Try one of these to start:</p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTED_PROMPTS.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setQuestion(s)}
                  className="rounded-full border px-3 py-1 hover:text-[var(--color-fg)]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          history.map((t, i) => <TurnView key={i} turn={t} datasetId={datasetId} />)
        )}
        {asking && (
          <div className="text-xs italic text-[var(--color-muted)]">
            Planning → validating → running → explaining…
          </div>
        )}
      </div>

      {error && (
        <div className="mt-3">
          <AIError error={error} onRetry={() => setError(null)} />
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
        className="mt-3 flex items-center gap-2"
      >
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about your data…"
          maxLength={500}
        />
        <Button type="submit" disabled={asking || !question.trim()}>
          Ask
        </Button>
      </form>
    </Card>
  );
}

function TurnView({ turn, datasetId }: { turn: RenderedTurn; datasetId: string }) {
  const isUser = turn.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          isUser
            ? "max-w-[78%] rounded-2xl rounded-tr-sm bg-[var(--color-accent)] px-3.5 py-2 text-sm text-white shadow-sm"
            : "max-w-full flex-1 space-y-3 rounded-2xl rounded-tl-sm border border-[var(--color-border)] bg-[var(--color-panel)] px-3.5 py-3 text-sm shadow-sm"
        }
      >
        {isUser ? (
          <p className="whitespace-pre-line">{turn.content}</p>
        ) : (
          <AssistantTurn turn={turn} datasetId={datasetId} />
        )}
      </div>
    </div>
  );
}

function AssistantTurn({ turn, datasetId }: { turn: RenderedTurn; datasetId: string }) {
  const payload = turn.payload;
  return (
    <>
      <p className="whitespace-pre-line text-sm">{turn.content}</p>
      {payload?.result_table && payload.result_table.row_count > 0 && (
        <ResultTableView table={payload.result_table} />
      )}
      {payload?.suggested_chart && payload.result_table && (
        <SuggestedChart
          datasetId={datasetId}
          chart={payload.suggested_chart}
        />
      )}
      {payload?.analysis_spec && (
        <details className="text-xs">
          <summary className="cursor-pointer text-[var(--color-muted)] hover:text-[var(--color-fg)]">
            How this was computed
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-[var(--color-bg)]/60 p-2 font-mono text-[10px] leading-relaxed text-[var(--color-muted)]">
            {JSON.stringify(payload.analysis_spec, null, 2)}
          </pre>
        </details>
      )}
    </>
  );
}

function ResultTableView({ table }: { table: AIResultTable }) {
  return (
    <div className="overflow-x-auto rounded border bg-[var(--color-bg)]/40">
      <table className="min-w-full text-xs">
        <thead className="border-b">
          <tr>
            {table.columns.map((c) => (
              <th key={c} className="px-2 py-1 text-left font-mono font-normal text-[var(--color-muted)]">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.slice(0, 25).map((row, i) => (
            <tr key={i} className="border-b last:border-0">
              {table.columns.map((c) => (
                <td key={c} className="px-2 py-1">
                  {row[c] === null || row[c] === undefined ? "—" : String(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.row_count > 25 && (
        <p className="border-t px-2 py-1 text-[10px] text-[var(--color-muted)]">
          showing first 25 of {table.row_count} rows
          {table.truncated && " (result truncated)"}
        </p>
      )}
    </div>
  );
}

function SuggestedChart({
  datasetId,
  chart,
}: {
  datasetId: string;
  chart: Record<string, unknown>;
}) {
  const [data, setData] = useState<ChartDataResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const spec = chart as unknown as ChartSpec;

  useEffect(() => {
    apiPost<ChartDataResponse>(`/datasets/${datasetId}/chart-data`, spec)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  if (err) return <p className="text-xs text-[var(--color-danger)]">chart: {err}</p>;
  if (!data) return <p className="text-xs text-[var(--color-muted)]">Loading chart…</p>;
  return (
    <div className="overflow-hidden rounded border bg-[var(--color-bg)]/40">
      <Chart spec={spec} data={data} height={220} />
    </div>
  );
}

"use client";

import { useState } from "react";
import { apiGet } from "@/lib/api";
import type { ChartHandle } from "@/components/charts/chart";
import type {
  AIInsightsResponse,
  AISummaryResponse,
  ChartSpec,
} from "@/types";
import { Button } from "@/components/ui/button";

interface Props {
  datasetId: string;
  datasetName: string;
  versionLabel: string;
  cleaningStepCount: number;
  // KPI specs (so we can label them) — KPIs render as cards, not chart PNGs.
  qualityScoreBefore?: number | null;
  qualityScoreAfter?: number | null;
  // The added charts on the dashboard, keyed by their grid id.
  charts: Array<{ key: string; spec: ChartSpec; handle: ChartHandle | null }>;
}

interface ReportState {
  busy: boolean;
  step: string;
  error: string | null;
}

const ASSEMBLE_STEPS = {
  fetching: "Loading AI sections…",
  capturing: "Capturing charts…",
  assembling: "Assembling PDF…",
} as const;

export function ExportReport(props: Props) {
  const [state, setState] = useState<ReportState>({ busy: false, step: "", error: null });

  async function exportPdf() {
    setState({ busy: true, step: ASSEMBLE_STEPS.fetching, error: null });
    try {
      // 1. AI sections — use cached content (no ?refresh).
      const ai = await loadAISections(props.datasetId);

      // 2. Chart PNGs — capture from registered handles. Skip KPI tiles.
      setState((s) => ({ ...s, step: ASSEMBLE_STEPS.capturing }));
      const chartImages: Array<{ title: string; png: string }> = [];
      for (const c of props.charts) {
        if (!c.handle || c.spec.chart_type === "kpi") continue;
        const png = await c.handle.toImage();
        if (png) chartImages.push({ title: c.spec.title ?? c.spec.chart_type, png });
      }

      // 3. Build the PDF.
      setState((s) => ({ ...s, step: ASSEMBLE_STEPS.assembling }));
      const { jsPDF } = await import("jspdf");
      const doc = new jsPDF({ unit: "pt", format: "a4" });
      buildPdf(doc, { ...props, ai, chartImages });

      const filename = safeName(props.datasetName) + "-report.pdf";
      doc.save(filename);
      setState({ busy: false, step: "", error: null });
    } catch (e) {
      setState({
        busy: false,
        step: "",
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="secondary"
        onClick={exportPdf}
        disabled={state.busy}
        className="text-xs"
      >
        {state.busy ? state.step : "Export report (PDF)"}
      </Button>
      {state.error && (
        <span className="text-xs text-[var(--color-danger)]">{state.error}</span>
      )}
    </div>
  );
}

// ===========================================================================
// AI loading (cached only; fall through to placeholders)
// ===========================================================================

interface AISections {
  summary: string | null;
  story: string | null;
  insights: AIInsightsResponse | null;
}

async function loadAISections(datasetId: string): Promise<AISections> {
  // We allow each fetch to fail independently — the report still ships with
  // a clear "not generated yet" placeholder.
  async function safeGet<T>(path: string): Promise<T | null> {
    try {
      return await apiGet<T>(path);
    } catch {
      return null;
    }
  }
  const [summary, story, insights] = await Promise.all([
    safeGet<AISummaryResponse>(`/datasets/${datasetId}/ai/summary`),
    safeGet<AISummaryResponse>(`/datasets/${datasetId}/ai/story`),
    safeGet<AIInsightsResponse>(`/datasets/${datasetId}/ai/insights`),
  ]);
  return {
    summary: summary?.text ?? null,
    story: story?.text ?? null,
    insights: insights ?? null,
  };
}

// ===========================================================================
// PDF assembly
// ===========================================================================

interface BuildArgs extends Props {
  ai: AISections;
  chartImages: Array<{ title: string; png: string }>;
}

type Doc = InstanceType<typeof import("jspdf")["jsPDF"]>;

const PAGE_MARGIN = 48;
const MAX_WIDTH = 595 - PAGE_MARGIN * 2; // A4 width
const PAGE_HEIGHT = 842;

function buildPdf(doc: Doc, args: BuildArgs) {
  let y = PAGE_MARGIN;

  // ---- Title block -------------------------------------------------------
  doc.setFontSize(20);
  doc.setFont("helvetica", "bold");
  y = writeLine(doc, args.datasetName, PAGE_MARGIN, y, 24);
  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  y = writeLine(
    doc,
    `Generated ${new Date().toLocaleString()}`,
    PAGE_MARGIN,
    y,
    14
  );
  const provenance =
    args.versionLabel === "cleaned"
      ? `Built on the cleaned version — ${args.cleaningStepCount} preprocessing step${
          args.cleaningStepCount === 1 ? "" : "s"
        } applied.`
      : "Built on the raw upload.";
  y = writeLine(doc, provenance, PAGE_MARGIN, y, 14);

  if (
    args.qualityScoreBefore !== null &&
    args.qualityScoreBefore !== undefined &&
    args.qualityScoreAfter !== null &&
    args.qualityScoreAfter !== undefined
  ) {
    y = writeLine(
      doc,
      `Data quality score: ${args.qualityScoreBefore} → ${args.qualityScoreAfter}.`,
      PAGE_MARGIN,
      y,
      14
    );
  }
  y += 8;

  // ---- Summary -----------------------------------------------------------
  y = section(doc, "Summary", y);
  y = paragraph(doc, args.ai.summary ?? "(AI summary not generated yet — open the AI page first.)", y);

  // ---- Data story --------------------------------------------------------
  y = section(doc, "Data story", y);
  y = paragraph(doc, args.ai.story ?? "(Data story not generated yet — open the AI page first.)", y);

  // ---- Insights ----------------------------------------------------------
  y = section(doc, "Key insights", y);
  if (!args.ai.insights || args.ai.insights.findings.length === 0) {
    y = paragraph(doc, "(No insights generated yet — open the AI page first.)", y);
  } else {
    for (const f of args.ai.insights.findings) {
      y = ensureSpace(doc, y, 60);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(11);
      y = writeLine(doc, `• ${f.title}  [${f.severity}]`, PAGE_MARGIN, y, 14);
      doc.setFont("helvetica", "normal");
      doc.setFontSize(10);
      y = paragraph(doc, f.detail, y);
    }
  }

  // ---- Charts ------------------------------------------------------------
  y = section(doc, "Dashboard charts", y);
  if (args.chartImages.length === 0) {
    y = paragraph(doc, "(No charts on this dashboard.)", y);
  } else {
    for (const c of args.chartImages) {
      y = ensureSpace(doc, y, 220);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(11);
      y = writeLine(doc, c.title, PAGE_MARGIN, y, 14);
      doc.setFont("helvetica", "normal");
      doc.setFontSize(10);
      const imgH = 200;
      try {
        doc.addImage(c.png, "PNG", PAGE_MARGIN, y, MAX_WIDTH, imgH);
        y += imgH + 16;
      } catch (e) {
        y = paragraph(doc, `(chart capture failed: ${e instanceof Error ? e.message : e})`, y);
      }
    }
  }

  // ---- Footer ------------------------------------------------------------
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(120);
    doc.text(
      `InsightForge — page ${i} of ${pages}`,
      PAGE_MARGIN,
      PAGE_HEIGHT - 24
    );
    doc.setTextColor(0);
  }
}

function section(doc: Doc, title: string, y: number): number {
  y = ensureSpace(doc, y, 48);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  const next = writeLine(doc, title, PAGE_MARGIN, y, 18);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  return next + 4;
}

function paragraph(doc: Doc, text: string, y: number): number {
  if (!text) return y + 4;
  // jspdf splits long text to fit width.
  const lines: string[] = doc.splitTextToSize(text, MAX_WIDTH);
  for (const line of lines) {
    y = ensureSpace(doc, y, 16);
    y = writeLine(doc, line, PAGE_MARGIN, y, 14);
  }
  return y + 6;
}

function writeLine(doc: Doc, text: string, x: number, y: number, lineHeight: number): number {
  doc.text(text, x, y);
  return y + lineHeight;
}

function ensureSpace(doc: Doc, y: number, needed: number): number {
  if (y + needed <= PAGE_HEIGHT - PAGE_MARGIN) return y;
  doc.addPage();
  return PAGE_MARGIN;
}

function safeName(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]+/g, "_") || "report";
}

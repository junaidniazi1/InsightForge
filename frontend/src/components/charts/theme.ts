"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

/**
 * Chart-engine palettes. Plotly + ECharts are canvas/SVG and don't read CSS
 * custom properties, so we mirror the design tokens here as JS constants and
 * pick the right one based on the active theme.
 */

export interface ChartTheme {
  paper: string;
  panel: string;
  bg: string;
  border: string;
  fg: string;
  muted: string;
  font: string;
  palette: string[];
}

// Tailwind family — same numbers used in globals.css so charts match the page.
const FONT_STACK =
  'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif';

const SHARED_PALETTE = [
  "#4f46e5", // indigo-600
  "#10b981", // emerald-500
  "#f59e0b", // amber-500
  "#e11d48", // rose-600
  "#0284c7", // sky-600
  "#a855f7", // purple-500
  "#14b8a6", // teal-500
  "#f97316", // orange-500
  "#84cc16", // lime-500
  "#06b6d4", // cyan-500
];

const SHARED_PALETTE_DARK = [
  "#818cf8", // indigo-400
  "#34d399", // emerald-400
  "#fbbf24", // amber-400
  "#fb7185", // rose-400
  "#38bdf8", // sky-400
  "#c084fc", // purple-400
  "#2dd4bf", // teal-400
  "#fb923c", // orange-400
  "#a3e635", // lime-400
  "#22d3ee", // cyan-400
];

export const LIGHT_THEME: ChartTheme = {
  paper: "#ffffff",
  panel: "#ffffff",
  bg: "#f8fafc",   // slate-50
  border: "#e2e8f0", // slate-200
  fg: "#0f172a",   // slate-900
  muted: "#64748b", // slate-500
  font: FONT_STACK,
  palette: SHARED_PALETTE,
};

export const DARK_THEME: ChartTheme = {
  paper: "#0f172a", // slate-900
  panel: "#0f172a",
  bg: "#020617",   // slate-950
  border: "#1e293b", // slate-800
  fg: "#f1f5f9",   // slate-100
  muted: "#94a3b8", // slate-400
  font: FONT_STACK,
  palette: SHARED_PALETTE_DARK,
};

// Back-compat: components that imported the old single-theme constant keep
// working. They read from this default until they migrate to useChartTheme().
export const CHART_THEME: ChartTheme = LIGHT_THEME;

// Named user-selectable palettes (Phase 6 chart editor) — keep both light
// and dark variants and pick by theme. Most palettes work fine in both, so
// these are designed to read on either background.
export const PALETTES: Record<string, string[]> = {
  default: SHARED_PALETTE,
  pastel: ["#a5d8ff", "#b2f2bb", "#ffec99", "#ffc9c9", "#d0bfff", "#99e9f2"],
  vivid: ["#ff6b6b", "#4dabf7", "#51cf66", "#ffd43b", "#cc5de8", "#15aabf"],
  monochrome: ["#94a3b8", "#cbd5e1", "#64748b", "#475569", "#e2e8f0", "#334155"],
  ocean: ["#06b6d4", "#0891b2", "#0e7490", "#155e75", "#164e63", "#22d3ee"],
  forest: ["#15803d", "#22c55e", "#84cc16", "#65a30d", "#16a34a", "#4ade80"],
};

export const PALETTE_NAMES = Object.keys(PALETTES);

export function paletteFor(name?: string): string[] {
  if (!name || name === "default") return SHARED_PALETTE;
  return PALETTES[name] ?? SHARED_PALETTE;
}

/**
 * Theme-aware hook for chart wrappers. Returns the resolved chart theme,
 * guarded against the next-themes hydration flash (renders LIGHT before
 * mount — matches the SSR default).
 */
export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return LIGHT_THEME;
  return resolvedTheme === "dark" ? DARK_THEME : LIGHT_THEME;
}

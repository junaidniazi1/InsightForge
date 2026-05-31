import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Heart,
  Sparkles,
  Wand2,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Dataset } from "@/types";

interface Props {
  dataset: Dataset;
  hasCleanedVersion: boolean;
  cleanedStepCount?: number;
}

interface Card {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  iconClass: string;
  status?: { label: string; variant: "neutral" | "info" | "success" };
  highlight?: boolean;
}

/**
 * Launchpad cards on the dataset home. Each card has a distinct icon (so the
 * eye picks the right one even before reading), a one-line description, and an
 * optional status badge (e.g. "1 cleaned version" / "ready" / "not run yet").
 */
export function CapabilityCards({ dataset, hasCleanedVersion, cleanedStepCount = 0 }: Props) {
  const cards: Card[] = [
    {
      href: `/sources/${dataset.id}/health`,
      title: "Data Health",
      description: "Profile the data, surface every issue, pick the fixes you want.",
      icon: Heart,
      iconClass: "text-rose-600 dark:text-rose-300 bg-rose-50 dark:bg-rose-500/10",
      status:
        dataset.status === "profiled" || dataset.status === "cleaned"
          ? { label: "ready", variant: "success" }
          : { label: "not run yet", variant: "neutral" },
    },
    {
      href: `/sources/${dataset.id}/clean`,
      title: "Clean & Download",
      description: hasCleanedVersion
        ? "Edit your pipeline or download the cleaned file directly."
        : "One-click auto-clean, or build a pipeline. Download CSV / XLSX when done.",
      icon: Wand2,
      iconClass: "text-indigo-600 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-500/10",
      status: hasCleanedVersion
        ? {
            label: `${cleanedStepCount > 0 ? cleanedStepCount + " step" + (cleanedStepCount === 1 ? "" : "s") : "cleaned"}`,
            variant: "success",
          }
        : { label: "not started", variant: "neutral" },
      highlight: true,
    },
    {
      href: `/sources/${dataset.id}/dashboard`,
      title: "Dashboard",
      description: "Auto-suggested charts, KPI cards, global filters, PDF export.",
      icon: BarChart3,
      iconClass: "text-sky-600 dark:text-sky-300 bg-sky-50 dark:bg-sky-500/10",
    },
    {
      href: `/sources/${dataset.id}/ai`,
      title: "AI Insights",
      description: "Summary, data story, key findings, and ‘Ask Your Data’.",
      icon: Sparkles,
      iconClass: "text-amber-600 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10",
    },
    {
      href: `/sources/${dataset.id}/workbench`,
      title: "Analyst Workbench",
      description: "Statistics, hypothesis tests, time-series, clustering, PCA, ML.",
      icon: Wrench,
      iconClass: "text-emerald-600 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/10",
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <Link
            key={c.title}
            href={c.href}
            className={
              "group flex flex-col gap-3 rounded-xl border bg-[var(--color-panel)] p-5 shadow-sm transition-all " +
              (c.highlight
                ? "border-[var(--color-accent)]/40 hover:border-[var(--color-accent)] hover:shadow-md"
                : "border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:shadow-md")
            }
          >
            <div className="flex items-start justify-between">
              <div className={"inline-flex h-10 w-10 items-center justify-center rounded-xl " + c.iconClass}>
                <Icon className="h-5 w-5" />
              </div>
              {c.status && (
                <Badge variant={c.status.variant} compact>
                  {c.status.label}
                </Badge>
              )}
            </div>
            <div>
              <h3 className="text-base font-medium text-[var(--color-fg)]">
                {c.title}
              </h3>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                {c.description}
              </p>
            </div>
            <div
              className={
                "mt-auto inline-flex items-center gap-1 text-xs font-medium transition-colors " +
                (c.highlight
                  ? "text-[var(--color-accent)]"
                  : "text-[var(--color-muted)] group-hover:text-[var(--color-fg)]")
              }
            >
              Open
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </div>
          </Link>
        );
      })}
    </div>
  );
}

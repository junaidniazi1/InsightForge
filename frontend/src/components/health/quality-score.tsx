import { clsx } from "clsx";

interface Props {
  score: number;
  breakdown: { reason: string; points: number }[];
}

function colorFor(score: number): { ring: string; text: string; label: string } {
  if (score >= 85) return { ring: "stroke-[var(--color-success)]", text: "text-[var(--color-success)]", label: "Healthy" };
  if (score >= 60) return { ring: "stroke-amber-400", text: "text-amber-400", label: "Some issues" };
  return { ring: "stroke-[var(--color-danger)]", text: "text-[var(--color-danger)]", label: "Needs cleaning" };
}

export function QualityScore({ score, breakdown }: Props) {
  const { ring, text, label } = colorFor(score);
  const r = 42;
  const c = 2 * Math.PI * r;
  const dash = (score / 100) * c;
  return (
    <div className="flex items-start gap-6">
      <div className="relative h-28 w-28 shrink-0">
        <svg className="h-28 w-28 -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r={r} fill="none" stroke="var(--color-border)" strokeWidth="8" />
          <circle
            cx="50"
            cy="50"
            r={r}
            fill="none"
            strokeWidth="8"
            strokeDasharray={`${dash} ${c}`}
            strokeLinecap="round"
            className={ring}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={clsx("text-3xl font-semibold", text)}>{score}</span>
          <span className="text-xs text-[var(--color-muted)]">/ 100</span>
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <p className={clsx("text-sm font-medium", text)}>{label}</p>
        <p className="mt-1 text-xs text-[var(--color-muted)]">Data quality score</p>
        {breakdown.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]">
              How was this calculated?
            </summary>
            <ul className="mt-2 space-y-1 text-xs">
              {breakdown.map((d, i) => (
                <li key={i} className="flex justify-between gap-4">
                  <span className="text-[var(--color-muted)]">{d.reason}</span>
                  <span className="font-mono text-[var(--color-danger)]">{d.points}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}

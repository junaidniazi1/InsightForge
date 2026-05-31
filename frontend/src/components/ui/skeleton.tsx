import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

/**
 * Shimmer block that takes the shape of whatever content is loading. Compose
 * `<SkeletonLine>` / `<SkeletonBlock>` / `<SkeletonChart>` / `<SkeletonTable>`
 * instead of writing "Loading…".
 */
function Skeleton({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...rest}
      aria-hidden="true"
      className={clsx(
        "animate-pulse rounded-md bg-[var(--color-border)]",
        className,
      )}
    />
  );
}

/** A line of fake text. Vary the width to look natural. */
export function SkeletonLine({
  width = "100%",
  height = 12,
  className,
}: {
  width?: string | number;
  height?: number;
  className?: string;
}) {
  return (
    <Skeleton
      className={clsx("rounded", className)}
      style={{ width, height }}
    />
  );
}

/** A solid block, defaults to chart-tile size. */
export function SkeletonBlock({
  height = 120,
  className,
}: {
  height?: number;
  className?: string;
}) {
  return <Skeleton className={clsx("w-full rounded-xl", className)} style={{ height }} />;
}

/** Chart-shaped: header line + body block. */
export function SkeletonChart({ height = 280 }: { height?: number }) {
  return (
    <div className="space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
      <SkeletonLine width="40%" height={12} />
      <SkeletonBlock height={height - 40} />
    </div>
  );
}

/** Table-shaped: header row + N body rows. */
export function SkeletonTable({
  columns = 5,
  rows = 6,
}: {
  columns?: number;
  rows?: number;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)]">
      <div
        className="grid border-b border-[var(--color-border)] bg-[var(--color-bg)] p-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gap: 12 }}
      >
        {Array.from({ length: columns }).map((_, i) => (
          <SkeletonLine key={i} height={10} />
        ))}
      </div>
      <div className="divide-y divide-[var(--color-border)]">
        {Array.from({ length: rows }).map((_, r) => (
          <div
            key={r}
            className="grid p-3"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gap: 12 }}
          >
            {Array.from({ length: columns }).map((_, c) => (
              <SkeletonLine key={c} height={10} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Stack of skeleton lines for AI text cards / paragraph-shaped content. */
export function SkeletonParagraph({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine
          key={i}
          width={i === lines - 1 ? "60%" : "100%"}
          height={10}
        />
      ))}
    </div>
  );
}

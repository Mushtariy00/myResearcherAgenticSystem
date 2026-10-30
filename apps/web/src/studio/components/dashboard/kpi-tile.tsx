"use client";

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { glassClassName } from "@/studio/lib/glass";
import type { Tone } from "@/studio/lib/stages";

export type KpiTileProps = {
  label: string;
  icon: LucideIcon;
  /** `null` while loading (a skeleton of the same size keeps the layout still). */
  value: number | null;
  format?: Intl.NumberFormatOptions;
  hint?: ReactNode;
  tone?: Tone;
  /** Extra content under the number, e.g. a progress bar. */
  children?: ReactNode;
  className?: string;
};

/** A dashboard metric: label, a spring-counted number with tabular figures, and a hint. */
export function KpiTile({
  label,
  icon: Icon,
  value,
  format,
  hint,
  tone = "info",
  children,
  className,
}: KpiTileProps) {
  return (
    <div className={cn(glassClassName(), "flex min-w-0 flex-col gap-3 p-4 sm:p-5", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-xs font-medium text-muted-foreground sm:text-sm">{label}</p>
        <span
          aria-hidden
          data-tone={tone}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-(--tone)/25 bg-(--tone)/12 text-(--tone-fg)"
        >
          <Icon className="size-4" />
        </span>
      </div>
      <div className="flex h-8 min-w-0 items-center font-mono text-xl font-semibold tracking-tight text-foreground sm:h-9 sm:text-2xl xl:text-3xl">
        {value === null ? (
          <ShimmerSkeleton className="h-7 w-24 sm:h-8" />
        ) : (
          <NumberTicker value={value} format={format} />
        )}
      </div>
      {children}
      {hint && <div className="min-h-4 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

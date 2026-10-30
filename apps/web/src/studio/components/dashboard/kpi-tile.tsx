"use client";

import { type LucideIcon, RotateCwIcon } from "lucide-react";
import { type ReactNode, useId } from "react";
import { cn } from "@/lib/utils";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { Sparkline } from "@/studio/components/effects/sparkline";
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
  /** Values for the sparkline under the number, oldest first. */
  trend?: readonly number[] | null;
  /** The source failed: the number reads as missing, and the hint offers a retry. */
  failed?: { message: string; retryLabel: string; onRetry: () => void } | null;
  /** Extra content under the number, e.g. a progress bar. */
  children?: ReactNode;
  className?: string;
};

/**
 * A dashboard metric: label, a spring-counted number with tabular figures, a sparkline of its
 * recent history and a hint. A group named by its label, so "Active runs, 3" reads together.
 */
export function KpiTile({
  label,
  icon: Icon,
  value,
  format,
  hint,
  tone = "info",
  trend,
  failed,
  children,
  className,
}: KpiTileProps) {
  const labelId = useId();
  return (
    // biome-ignore lint/a11y/useSemanticElements: a metric is not a set of form fields (fieldset)
    <div
      role="group"
      aria-labelledby={labelId}
      data-tone={tone}
      className={cn(glassClassName(), "flex min-w-0 flex-col gap-3 p-4 sm:p-5", className)}
    >
      <div className="flex items-center justify-between gap-2">
        <p id={labelId} className="min-w-0 text-xs font-medium text-muted-foreground sm:text-sm">
          {label}
        </p>
        <span
          aria-hidden
          className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-(--tone)/25 bg-(--tone)/12 text-(--tone-fg)"
        >
          <Icon className="size-4" />
        </span>
      </div>
      <div className="flex h-8 min-w-0 items-center font-mono text-xl font-semibold tracking-tight text-foreground sm:h-9 sm:text-2xl xl:text-3xl">
        {failed ? (
          <span aria-hidden>—</span>
        ) : value === null ? (
          <ShimmerSkeleton className="h-7 w-24 sm:h-8" />
        ) : (
          <NumberTicker value={value} format={format} />
        )}
      </div>
      {children}
      <div className="mt-auto grid gap-2">
        {trend && !failed && <Sparkline values={trend} className="h-7" />}
        {failed ? (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>{failed.message}</span>
            <button
              type="button"
              onClick={failed.onRetry}
              className="inline-flex items-center gap-1 rounded-md font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <RotateCwIcon aria-hidden className="size-3" />
              {failed.retryLabel}
            </button>
          </p>
        ) : (
          hint && <div className="min-h-4 text-xs text-muted-foreground">{hint}</div>
        )}
      </div>
    </div>
  );
}

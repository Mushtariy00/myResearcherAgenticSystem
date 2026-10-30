"use client";

import { Meter } from "@base-ui/react/meter";
import { Progress } from "@base-ui/react/progress";
import { cn } from "@/lib/utils";

export type GaugeTone = "default" | "warning" | "danger";

type GaugeProps = {
  label: string;
  value: number;
  max?: number;
  /** The value as people read it ("62%", "9.8 GB of 24 GB"); also what screen readers hear. */
  valueText: string;
  tone?: GaugeTone;
  className?: string;
};

function fillClass(tone: GaugeTone): string {
  return tone === "default" ? "bg-primary" : "bg-(--tone)";
}

/** A labelled reading within a known range (GPU load, memory, budget used): a `meter`. */
export function Gauge({
  label,
  value,
  max = 100,
  valueText,
  tone = "default",
  className,
}: GaugeProps) {
  return (
    <Meter.Root
      value={Math.min(Math.max(value, 0), max)}
      max={max}
      aria-valuetext={valueText}
      className={cn("grid grid-cols-[1fr_auto] items-baseline gap-x-2 gap-y-1.5", className)}
    >
      <Meter.Label className="text-xs font-medium text-muted-foreground">{label}</Meter.Label>
      <span aria-hidden className="text-xs tabular-nums">
        {valueText}
      </span>
      <Meter.Track className="col-span-2 h-2 overflow-hidden rounded-full bg-muted">
        <Meter.Indicator
          data-tone={tone === "default" ? undefined : tone}
          className={cn(
            "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
            fillClass(tone),
          )}
        />
      </Meter.Track>
    </Meter.Root>
  );
}

/** How far a job has got: a `progressbar`. */
export function ProgressBar({ label, value, max = 100, valueText, className }: GaugeProps) {
  return (
    <Progress.Root
      value={Math.min(Math.max(value, 0), max)}
      max={max}
      aria-valuetext={valueText}
      className={cn("grid grid-cols-[1fr_auto] items-baseline gap-x-2 gap-y-1", className)}
    >
      <Progress.Label className="text-xs text-muted-foreground">{label}</Progress.Label>
      <span aria-hidden className="text-xs tabular-nums">
        {valueText}
      </span>
      <Progress.Track className="col-span-2 h-1.5 overflow-hidden rounded-full bg-muted">
        <Progress.Indicator className="h-full rounded-full bg-primary transition-[width] duration-500 motion-reduce:transition-none" />
      </Progress.Track>
    </Progress.Root>
  );
}

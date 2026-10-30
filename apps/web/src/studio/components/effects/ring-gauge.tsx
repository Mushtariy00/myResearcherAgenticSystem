import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type RingGaugeProps = {
  /** Between 0 and `max`; values outside are clamped. */
  value: number;
  max?: number;
  /** Diameter in pixels. */
  size?: number;
  /** Ring thickness in pixels. */
  thickness?: number;
  /** What the ring measures, e.g. "GPU utilisation" (the ring is a `meter`). */
  label: string;
  /** The spoken value, e.g. "87%" (defaults to the number). */
  valueText?: string;
  /** Shown inside the ring, e.g. a NumberTicker. */
  children?: ReactNode;
  className?: string;
};

/**
 * A circular gauge (a `meter` for assistive technology) in the surrounding tone (`--tone`, from
 * `data-tone` or `data-stage`). The arc eases to each new value (a stroke on a small SVG, not
 * transform or opacity, so it costs one tiny repaint) and moves at once with reduced motion.
 */
export function RingGauge({
  value,
  max = 100,
  size = 128,
  thickness = 10,
  label,
  valueText,
  children,
  className,
}: RingGaugeProps) {
  const share = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  const center = size / 2;
  const radius = (size - thickness) / 2;
  return (
    // biome-ignore lint/a11y/useSemanticElements: a native <meter> cannot draw the ring or hold content
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.round(Math.min(max, Math.max(0, value)))}
      aria-valuetext={valueText}
      className={cn("relative inline-grid shrink-0 place-items-center", className)}
      style={{ width: size, height: size }}
    >
      <svg
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden
        focusable="false"
        className="absolute inset-0 size-full -rotate-90"
      >
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          className="stroke-[color-mix(in_oklch,var(--foreground)_10%,transparent)]"
        />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray="100 100"
          strokeDashoffset={100 - share * 100}
          opacity={share > 0 ? 1 : 0}
          className="stroke-(--tone) transition-[stroke-dashoffset,opacity] duration-700 ease-out motion-reduce:transition-none"
        />
      </svg>
      <div className="relative grid place-items-center text-center">{children}</div>
    </div>
  );
}

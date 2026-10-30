import { useId } from "react";
import { cn } from "@/lib/utils";

const WIDTH = 100;
const HEIGHT = 32;
/** Room above and below the line, so its stroke and rounded joins are never clipped. */
const INSET = 2;

/** SVG path data of the line through `values`, scaled to the box (zero at the bottom). */
export function sparklinePath(values: readonly number[]): string {
  if (values.length === 0) {
    return "";
  }
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const range = max - min || 1;
  const step = values.length > 1 ? WIDTH / (values.length - 1) : 0;
  return values
    .map((value, index) => {
      const x = values.length > 1 ? index * step : WIDTH / 2;
      const y = HEIGHT - INSET - ((value - min) / range) * (HEIGHT - INSET * 2);
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

/**
 * A small trend line with a soft fill, in the surrounding tone (`--tone`, from `data-tone` or
 * `data-stage`). Decorative: the number it accompanies says what matters, so it is hidden from
 * assistive technology. It stretches to its box; the stroke keeps its width.
 */
export function Sparkline({
  values,
  className,
}: {
  values: readonly number[];
  className?: string;
}) {
  const gradient = `sparkline-${useId().replace(/[^\w-]/g, "")}`;
  const line = sparklinePath(values);
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="none"
      aria-hidden
      focusable="false"
      data-slot="sparkline"
      className={cn("block h-8 w-full overflow-visible text-(--tone,currentColor)", className)}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.26" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {values.length > 1 && (
        <path d={`${line} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z`} fill={`url(#${gradient})`} />
      )}
      {line && (
        <path
          d={line}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

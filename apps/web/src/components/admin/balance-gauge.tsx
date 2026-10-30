"use client";

import { useFormatter, useTranslations } from "next-intl";
import { USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { BalanceGaugeValue } from "./admin-format";

/** The upper half of a circle, left to right: centre (100, 100), radius 80. */
export const GAUGE_ARC = "M 20 100 A 80 80 0 0 1 180 100";

/** A point on the gauge arc at `share` (0 = left end, 1 = right end), `radius` from the centre. */
export function gaugePoint(share: number, radius: number): { x: number; y: number } {
  const angle = Math.PI * (1 - Math.min(1, Math.max(0, share)));
  return { x: 100 + radius * Math.cos(angle), y: 100 - radius * Math.sin(angle) };
}

const TONES = {
  success: "stroke-emerald-500",
  warning: "stroke-amber-500",
  danger: "stroke-destructive",
} as const;

/**
 * A half-circle meter of the lab balance against this month's funds, with a tick at the alert
 * floor. The numbers are in the markup next to it; the meter itself is labelled for assistive
 * technology.
 */
export function BalanceGauge({
  value,
  className,
}: {
  value: BalanceGaugeValue;
  className?: string;
}) {
  const t = useTranslations("admin.balance");
  const format = useFormatter();
  const percent = Math.round(value.share * 100);
  const amount = format.number(value.balance, USD);
  const floorInner = gaugePoint(value.floorShare, 66);
  const floorOuter = gaugePoint(value.floorShare, 94);

  return (
    // biome-ignore lint/a11y/useSemanticElements: the meter is drawn in SVG, which <meter> cannot hold
    <div
      role="meter"
      aria-label={t("gauge")}
      aria-valuemin={0}
      aria-valuemax={value.funds}
      aria-valuenow={value.balance}
      aria-valuetext={t("gaugeValue", { amount, percent })}
      className={cn("relative mx-auto w-full max-w-64", className)}
    >
      <svg viewBox="0 0 200 110" className="w-full" aria-hidden>
        <path
          d={GAUGE_ARC}
          pathLength={100}
          fill="none"
          strokeWidth={16}
          strokeLinecap="round"
          className="stroke-muted"
        />
        {value.share > 0 && (
          <path
            d={GAUGE_ARC}
            pathLength={100}
            fill="none"
            strokeWidth={16}
            strokeLinecap="round"
            strokeDasharray={`${value.share * 100} 100`}
            className={TONES[value.tone]}
          />
        )}
        {value.floorShare > 0 && (
          <line
            x1={floorInner.x}
            y1={floorInner.y}
            x2={floorOuter.x}
            y2={floorOuter.y}
            strokeWidth={2.5}
            strokeLinecap="round"
            className="stroke-foreground/70"
          />
        )}
      </svg>
      <div className="absolute inset-x-0 bottom-0 grid justify-items-center gap-0.5">
        <span className="text-2xl font-semibold tabular-nums">{amount}</span>
        <span className="text-xs text-muted-foreground">{t("left", { percent })}</span>
      </div>
    </div>
  );
}

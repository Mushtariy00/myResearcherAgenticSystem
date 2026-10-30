"use client";

import { ArrowDownIcon, ArrowUpIcon } from "lucide-react";
import { type NumberFormatOptions, useFormatter, useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

export type MetricProps = {
  label: string;
  /** Missing measurements stay missing (null), never 0. */
  value: number | null | undefined;
  /** Shows which way is better; omit for values without a direction. */
  higherIsBetter?: boolean;
  /** Number format (locale-aware); default: up to 3 fraction digits. */
  format?: NumberFormatOptions;
  /** Text after the number, e.g. "ms". */
  unit?: string;
  size?: "sm" | "default" | "lg";
  className?: string;
};

const VALUE_SIZES = { sm: "text-sm", default: "text-lg", lg: "text-2xl" } as const;

/** A labelled number in tabular figures, with an arrow for the direction that is better. */
export function Metric({
  label,
  value,
  higherIsBetter,
  format,
  unit,
  size = "default",
  className,
}: MetricProps) {
  const t = useTranslations("shared.metric");
  const formatter = useFormatter();
  const missing = value === null || value === undefined || !Number.isFinite(value);
  const direction =
    higherIsBetter === undefined ? null : higherIsBetter ? t("higherIsBetter") : t("lowerIsBetter");
  const Arrow = higherIsBetter ? ArrowUpIcon : ArrowDownIcon;
  return (
    <dl data-slot="metric" className={cn("flex min-w-0 flex-col gap-0.5", className)}>
      <dt className="truncate text-xs text-muted-foreground">{label}</dt>
      <dd className="flex items-baseline gap-1.5">
        <span className={cn("font-semibold tabular-nums", VALUE_SIZES[size])}>
          {missing ? (
            <>
              <span aria-hidden>—</span>
              <span className="sr-only">{t("notMeasured")}</span>
            </>
          ) : (
            formatter.number(value, format ?? { maximumFractionDigits: 3 })
          )}
        </span>
        {unit && !missing && <span className="text-xs text-muted-foreground">{unit}</span>}
        {direction && (
          <span
            className="inline-flex items-center gap-0.5 text-xs text-muted-foreground"
            title={direction}
          >
            <Arrow aria-hidden className="size-3" />
            <span className="sr-only">{direction}</span>
          </span>
        )}
      </dd>
    </dl>
  );
}

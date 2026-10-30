"use client";

import type { EChartsType } from "echarts/core";
import { TableIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { resolveColors } from "@/components/shared/css-color";
import { DemoBadge } from "@/components/shared/demo-badge";
import { useThemeKey } from "@/components/shared/use-dom";
import { USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import { GHOST_BUTTON } from "@/studio/lib/ui";
import type { SpendDay } from "./dashboard-data";
import { buildSpendOption, type SpendChartLabels, type SpendChartTheme } from "./spend-option";
import { StudioInlineError, StudioPanel } from "./studio-panel";

/** The Studio colours as the chart's canvas needs them, read where the chart is. */
function readTheme(scope: HTMLElement): SpendChartTheme {
  const colors = resolveColors(scope, {
    barFrom: "var(--aurora-violet, #8b5cf6)",
    barTo: "color-mix(in oklch, var(--aurora-indigo, #6366f1) 55%, transparent)",
    text: "var(--muted-foreground, GrayText)",
    axis: "color-mix(in oklch, var(--foreground, CanvasText) 22%, transparent)",
    grid: "color-mix(in oklch, var(--foreground, CanvasText) 8%, transparent)",
  });
  return {
    ...colors,
    tooltip: {
      background: "var(--popover, Canvas)",
      foreground: "var(--popover-foreground, CanvasText)",
      border: "var(--studio-glass-border, GrayText)",
    },
    fontFamily: getComputedStyle(scope).fontFamily,
  };
}

/**
 * Paid spend per day over the usage window (30 UTC days), as ECharts bars in the aurora colours
 * (ECharts loads on demand, in the browser only). The same figures are in a data table for
 * screen readers, which sighted users can open too.
 */
export function SpendChart({
  days,
  total,
  demo,
  loading,
  error,
  onRetry,
  className,
}: {
  days: readonly SpendDay[];
  /** Paid spend over the whole window. */
  total: number;
  demo: boolean;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  className?: string;
}) {
  const t = useTranslations("studioWork.dashboard.spend");
  const tCommon = useTranslations("common");
  const tChart = useTranslations("shared.chart");
  const format = useFormatter();
  const tableId = useId();
  const plot = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const [ready, setReady] = useState(false);
  const [tableOpen, setTableOpen] = useState(false);
  const reducedMotion = useReducedMotionPreference();
  const themeKey = useThemeKey();
  const hasData = days.some((day) => day.paidUsd > 0 || day.paidCalls > 0 || day.freeCalls > 0);

  const labels = useMemo<SpendChartLabels>(
    () => ({
      paid: t("paid"),
      paidCalls: t("paidCalls"),
      freeCalls: t("freeCalls"),
      formatDay: (day) =>
        format.dateTime(new Date(`${day}T00:00:00Z`), {
          month: "short",
          day: "numeric",
          timeZone: "UTC",
        }),
      formatUsd: (amount) => format.number(amount, USD),
      formatCount: (count) => format.number(count),
    }),
    [t, format],
  );

  useEffect(() => {
    const element = plot.current;
    if (!element || !hasData) {
      return;
    }
    let disposed = false;
    let observer: ResizeObserver | undefined;
    let frame = 0;
    import("./spend-chart-echarts")
      .then(({ init }) => {
        if (disposed) {
          return;
        }
        const instance = init(element, null, { renderer: "canvas" });
        chart.current = instance;
        if (typeof ResizeObserver !== "undefined") {
          observer = new ResizeObserver(() => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => instance.resize());
          });
          observer.observe(element);
        }
        setReady(true);
      })
      .catch(() => {
        // The data table still carries every value.
      });
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      chart.current?.dispose();
      chart.current = null;
      setReady(false);
    };
  }, [hasData]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: themeKey signals new CSS colours
  useEffect(() => {
    const element = plot.current;
    if (!ready || !element || !chart.current) {
      return;
    }
    chart.current.setOption(
      buildSpendOption({ days, theme: readTheme(element), labels, reducedMotion }),
      { notMerge: true },
    );
  }, [ready, days, labels, reducedMotion, themeKey]);

  return (
    <StudioPanel
      id="studio-spend"
      title={t("title")}
      description={t("description")}
      busy={loading}
      className={className}
      badge={<DemoBadge demo={demo} />}
      action={
        !loading && !error ? (
          <p className="text-right font-mono text-lg font-semibold tracking-tight text-foreground tabular-nums">
            {format.number(total, USD)}
            <span className="block font-sans text-xs font-normal tracking-normal text-muted-foreground">
              {t("total")}
            </span>
          </p>
        ) : null
      }
    >
      {loading ? (
        <>
          <LoadingStatus label={tCommon("loading")} />
          <ShimmerSkeleton className="h-56 rounded-xl" />
        </>
      ) : error ? (
        <StudioInlineError error={error} onRetry={onRetry} />
      ) : !hasData ? (
        <p className="rounded-xl border border-dashed border-(--studio-glass-border) px-4 py-10 text-center text-sm text-muted-foreground">
          {t("empty")}
        </p>
      ) : (
        <figure className="grid min-w-0 gap-2" aria-label={t("title")}>
          <div ref={plot} aria-hidden className="h-56 w-full min-w-0" />
          <button
            type="button"
            className={cn(GHOST_BUTTON, "h-8 w-fit px-2.5 text-xs")}
            aria-expanded={tableOpen}
            aria-controls={tableId}
            onClick={() => setTableOpen((open) => !open)}
          >
            <TableIcon aria-hidden />
            {tableOpen ? tChart("hideTable") : tChart("showTable")}
          </button>
          <div
            id={tableId}
            className={
              tableOpen
                ? "max-h-72 overflow-auto rounded-xl border border-(--studio-glass-border)"
                : "sr-only"
            }
          >
            <table className="w-full text-xs">
              <caption className="sr-only">{t("tableCaption")}</caption>
              <thead className="sticky top-0 bg-(--studio-surface)">
                <tr>
                  <th scope="col" className="px-3 py-1.5 text-left font-medium">
                    {t("day")}
                  </th>
                  <th scope="col" className="px-3 py-1.5 text-right font-medium">
                    {labels.paid}
                  </th>
                  <th scope="col" className="px-3 py-1.5 text-right font-medium">
                    {labels.paidCalls}
                  </th>
                  <th scope="col" className="px-3 py-1.5 text-right font-medium">
                    {labels.freeCalls}
                  </th>
                </tr>
              </thead>
              <tbody>
                {days.map((day) => (
                  <tr key={day.day} className="border-t border-(--studio-glass-border)">
                    <th scope="row" className="px-3 py-1.5 text-left font-normal tabular-nums">
                      {labels.formatDay(day.day)}
                    </th>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {labels.formatUsd(day.paidUsd)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {labels.formatCount(day.paidCalls)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {labels.formatCount(day.freeCalls)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </figure>
      )}
    </StudioPanel>
  );
}

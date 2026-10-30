"use client";

import type { EChartsType } from "echarts/core";
import { TableIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { MetricSeries } from "@/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { resolveColors } from "./css-color";
import {
  buildMetricsOption,
  type ChartTheme,
  type MetricsChartLabels,
  seriesData,
  seriesIds,
} from "./metrics-option";
import { useReducedMotion, useThemeKey } from "./use-dom";

/** Light-theme defaults, used only if shared.css is missing. */
const FALLBACK_SERIES = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#6250d6",
  "#e34948",
];

/** Chart colours as they apply inside `scope` (Classic, dark, or a Studio override). */
function readChartTheme(scope: HTMLElement): ChartTheme {
  const series: Record<string, string> = Object.fromEntries(
    FALLBACK_SERIES.map((fallback, index) => [
      String(index),
      `var(--chart-series-${index + 1}, ${fallback})`,
    ]),
  );
  const seriesColors = resolveColors(scope, series);
  const chrome = resolveColors(scope, {
    text: "var(--chart-text, var(--muted-foreground, GrayText))",
    axis: "var(--chart-axis, color-mix(in oklch, var(--foreground, CanvasText) 25%, transparent))",
    grid: "var(--chart-grid, color-mix(in oklch, var(--foreground, CanvasText) 9%, transparent))",
  });
  return {
    series: FALLBACK_SERIES.map((fallback, index) => seriesColors[String(index)] ?? fallback),
    text: chrome.text,
    axis: chrome.axis,
    grid: chrome.grid,
    tooltip: {
      background: "var(--chart-tooltip-bg, var(--popover, Canvas))",
      foreground: "var(--chart-tooltip-fg, var(--popover-foreground, CanvasText))",
      border: "var(--chart-tooltip-border, var(--border, GrayText))",
    },
    fontFamily: getComputedStyle(scope).fontFamily,
  };
}

export type MetricsChartProps = {
  /** Training curves, e.g. `ExperimentOutput.series`. */
  series: readonly MetricSeries[];
  /** Accessible name, shown as the caption unless `hideTitle`. */
  title: string;
  hideTitle?: boolean;
  /** Stable metric list for colours when this chart shows a subset (see `metricOrder`). */
  metricOrder?: readonly string[];
  /** CSS height of the plot; default 18rem. */
  height?: string;
  /** Shown instead of the plot while no point has a value; default "No metrics were recorded." */
  emptyText?: string;
  /**
   * The series grow while the chart is on screen (live training): updates merge the lines by
   * id, so a new epoch extends them instead of every line being drawn again.
   */
  live?: boolean;
  className?: string;
};

/**
 * Metric curves per epoch with ECharts (loaded on demand, client only). Train lines are solid,
 * validation dashed, test dotted; missing values leave gaps; the tooltip shows which direction
 * is better. Colours come from CSS variables and follow light, dark and the Studio theme. The
 * same numbers are in a data table for screen readers, which sighted users can open too.
 */
export function MetricsChart({
  series,
  title,
  hideTitle = false,
  metricOrder,
  height = "18rem",
  emptyText,
  live = false,
  className,
}: MetricsChartProps) {
  const t = useTranslations("shared.chart");
  const tMetric = useTranslations("shared.metric");
  const format = useFormatter();
  const titleId = useId();
  const tableId = useId();
  const plot = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const [ready, setReady] = useState(false);
  const [tableOpen, setTableOpen] = useState(false);
  const reducedMotion = useReducedMotion();
  const themeKey = useThemeKey();

  const labels = useMemo<MetricsChartLabels>(
    () => ({
      epoch: t("epoch"),
      split: { train: t("splits.train"), val: t("splits.val"), test: t("splits.test") },
      seriesName: (metric, split) => t("series", { metric, split }),
      higherIsBetter: tMetric("higherIsBetter"),
      lowerIsBetter: tMetric("lowerIsBetter"),
      noValue: t("noValue"),
      formatValue: (value) => format.number(value, { maximumSignificantDigits: 4 }),
      formatEpoch: (epoch) => format.number(epoch, { maximumFractionDigits: 0 }),
    }),
    [t, tMetric, format],
  );

  const hasData = series.some((entry) => entry.points.some((point) => point.value !== null));

  useEffect(() => {
    const element = plot.current;
    if (!element || !hasData) {
      return;
    }
    let disposed = false;
    let observer: ResizeObserver | undefined;
    let frame = 0;
    import("./metrics-chart-echarts")
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
      buildMetricsOption({
        series,
        theme: readChartTheme(element),
        labels,
        metricOrder,
        reducedMotion,
      }),
      // Series missing from the new option are removed either way.
      live ? { replaceMerge: ["series"] } : { notMerge: true },
    );
  }, [ready, series, labels, metricOrder, reducedMotion, themeKey, live]);

  const table = useMemo(() => {
    const ids = seriesIds(series);
    const columns = series.map((entry, index) => ({
      id: ids[index] ?? `${index}`,
      name: labels.seriesName(entry.name, labels.split[entry.split]),
      values: new Map(seriesData(entry)),
    }));
    const epochs = [...new Set(columns.flatMap((column) => [...column.values.keys()]))].sort(
      (a, b) => a - b,
    );
    return { columns, epochs };
  }, [series, labels]);

  return (
    <figure
      data-slot="metrics-chart"
      aria-labelledby={titleId}
      className={cn("grid min-w-0 gap-2", className)}
    >
      <figcaption id={titleId} className={hideTitle ? "sr-only" : "text-sm font-medium"}>
        {title}
      </figcaption>
      {hasData ? (
        <div ref={plot} aria-hidden className="w-full min-w-0" style={{ height }} />
      ) : (
        <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          {emptyText ?? t("empty")}
        </p>
      )}
      {hasData && (
        <>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            className="w-fit text-muted-foreground"
            aria-expanded={tableOpen}
            aria-controls={tableId}
            onClick={() => setTableOpen((open) => !open)}
          >
            <TableIcon aria-hidden />
            {tableOpen ? t("hideTable") : t("showTable")}
          </Button>
          <div
            id={tableId}
            className={tableOpen ? "max-h-72 overflow-auto rounded-lg border" : "sr-only"}
          >
            <table className="w-full text-xs">
              <caption className="sr-only">{t("tableCaption", { title })}</caption>
              <thead className="sticky top-0 bg-muted">
                <tr>
                  <th scope="col" className="px-2 py-1 text-left font-medium">
                    {labels.epoch}
                  </th>
                  {table.columns.map((column) => (
                    <th key={column.id} scope="col" className="px-2 py-1 text-right font-medium">
                      {column.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.epochs.map((epoch) => (
                  <tr key={epoch} className="border-t">
                    <th scope="row" className="px-2 py-1 text-left font-normal tabular-nums">
                      {labels.formatEpoch(epoch)}
                    </th>
                    {table.columns.map((column) => {
                      const value = column.values.get(epoch);
                      return (
                        <td key={column.id} className="px-2 py-1 text-right tabular-nums">
                          {value === null || value === undefined
                            ? labels.noValue
                            : labels.formatValue(value)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </figure>
  );
}

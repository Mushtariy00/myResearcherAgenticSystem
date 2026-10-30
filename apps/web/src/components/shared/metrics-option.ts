import type { LineSeriesOption } from "echarts/charts";
import type {
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { ComposeOption } from "echarts/core";
import type { MetricSeries } from "@/client";

/**
 * Pure ECharts option building for MetricsChart (no chart runtime here, so it is unit-tested).
 * Colour follows the metric (train, val and test of one metric share it), the split sets the
 * line style, missing values are gaps, and the tooltip names the better direction.
 */

export type MetricsChartOption = ComposeOption<
  LineSeriesOption | GridComponentOption | LegendComponentOption | TooltipComponentOption
>;

export type ChartTheme = {
  /** Categorical series colours in slot order (canvas-ready). */
  series: readonly string[];
  /** Axis labels, legend and axis name. */
  text: string;
  axis: string;
  grid: string;
  /** CSS colours for the HTML tooltip; CSS variables are fine (it renders inside the chart). */
  tooltip: { background: string; foreground: string; border: string };
  fontFamily?: string;
};

export type MetricsChartLabels = {
  epoch: string;
  split: Record<MetricSeries["split"], string>;
  /** "loss (Validation)" */
  seriesName: (metric: string, split: string) => string;
  higherIsBetter: string;
  lowerIsBetter: string;
  noValue: string;
  formatValue: (value: number) => string;
  formatEpoch: (epoch: number) => string;
};

export type MetricsOptionInput = {
  series: readonly MetricSeries[];
  theme: ChartTheme;
  labels: MetricsChartLabels;
  /**
   * The full, stable list of metric names that colours are assigned from. Pass it when showing
   * a subset, so a metric keeps its colour (default: names in order of appearance).
   */
  metricOrder?: readonly string[];
  reducedMotion?: boolean;
};

export const LINE_STYLES: Record<MetricSeries["split"], "solid" | "dashed" | "dotted"> = {
  train: "solid",
  val: "dashed",
  test: "dotted",
};

const SHOW_SYMBOLS_UP_TO = 30;

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Unique, stable ids: "loss:val", or "loss:val:2" for a repeated pair. */
export function seriesIds(series: readonly MetricSeries[]): string[] {
  const seen = new Map<string, number>();
  return series.map((entry) => {
    const base = `${entry.name}:${entry.split}`;
    const count = (seen.get(base) ?? 0) + 1;
    seen.set(base, count);
    return count === 1 ? base : `${base}:${count}`;
  });
}

/** The colour slot of each metric name. */
export function metricSlots(
  series: readonly MetricSeries[],
  metricOrder?: readonly string[],
): Map<string, number> {
  const slots = new Map<string, number>();
  for (const name of [...(metricOrder ?? []), ...series.map((entry) => entry.name)]) {
    if (!slots.has(name)) {
      slots.set(name, slots.size);
    }
  }
  return slots;
}

/** Points sorted by epoch; non-finite values become null (a gap, never a zero). */
export function seriesData(series: MetricSeries): [number, number | null][] {
  return [...series.points]
    .filter((point) => Number.isFinite(point.epoch))
    .sort((a, b) => a.epoch - b.epoch)
    .map((point) => [
      point.epoch,
      point.value !== null && Number.isFinite(point.value) ? point.value : null,
    ]);
}

/** A point is isolated when no neighbour has a value, so only a marker can show it. */
function hasIsolatedPoint(data: readonly [number, number | null][]): boolean {
  return data.some(
    ([, value], index) =>
      value !== null &&
      (data[index - 1]?.[1] ?? null) === null &&
      (data[index + 1]?.[1] ?? null) === null,
  );
}

type TooltipParam = {
  seriesId?: string;
  seriesName?: string;
  marker?: unknown;
  value?: unknown;
  axisValue?: unknown;
};

export function buildMetricsOption({
  series,
  theme,
  labels,
  metricOrder,
  reducedMotion = false,
}: MetricsOptionInput): MetricsChartOption {
  const ids = seriesIds(series);
  const slots = metricSlots(series, metricOrder);
  const palette = theme.series.length > 0 ? theme.series : ["currentColor"];
  const directions = new Map(series.map((entry, index) => [ids[index], entry.higher_is_better]));

  const lines: LineSeriesOption[] = series.map((entry, index) => {
    const data = seriesData(entry);
    const color = palette[(slots.get(entry.name) ?? 0) % palette.length];
    const showSymbol = data.length <= SHOW_SYMBOLS_UP_TO || hasIsolatedPoint(data);
    return {
      type: "line",
      id: ids[index],
      name: labels.seriesName(entry.name, labels.split[entry.split]),
      data,
      connectNulls: false,
      showSymbol,
      symbol: "circle",
      symbolSize: 6,
      lineStyle: { width: 2, type: LINE_STYLES[entry.split], color },
      itemStyle: { color },
      emphasis: { focus: "series" },
      z: entry.split === "train" ? 2 : 3,
    };
  });

  const formatter = (raw: unknown): string => {
    const params = (Array.isArray(raw) ? raw : [raw]) as TooltipParam[];
    const first = params[0];
    const epochValue = Array.isArray(first?.value) ? first.value[0] : first?.axisValue;
    const epoch =
      typeof epochValue === "number"
        ? labels.formatEpoch(epochValue)
        : escapeHtml(String(epochValue ?? ""));
    const rows = params
      .map((param) => {
        const value = Array.isArray(param.value) ? param.value[1] : undefined;
        const shown =
          typeof value === "number" && Number.isFinite(value)
            ? escapeHtml(labels.formatValue(value))
            : escapeHtml(labels.noValue);
        const higher = param.seriesId ? directions.get(param.seriesId) : undefined;
        const direction =
          higher === undefined
            ? ""
            : `<span style="opacity:.75">${higher ? "↑" : "↓"} ${escapeHtml(
                higher ? labels.higherIsBetter : labels.lowerIsBetter,
              )}</span>`;
        // ECharts builds `marker` itself (a coloured dot); everything else is escaped.
        const marker = typeof param.marker === "string" ? param.marker : "";
        return `<tr><td style="padding:1px 8px 1px 0">${marker}${escapeHtml(
          param.seriesName ?? "",
        )}</td><td style="padding:1px 8px 1px 0;text-align:right;font-variant-numeric:tabular-nums;font-weight:600">${shown}</td><td style="padding:1px 0">${direction}</td></tr>`;
      })
      .join("");
    return `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(labels.epoch)} ${epoch}</div><table style="border-collapse:collapse">${rows}</table>`;
  };

  return {
    animation: !reducedMotion,
    animationDuration: 300,
    textStyle: { color: theme.text, fontFamily: theme.fontFamily },
    grid: { left: 8, right: 16, top: 16, bottom: 64 },
    legend: {
      type: "plain",
      bottom: 0,
      left: 0,
      itemWidth: 22,
      itemHeight: 8,
      textStyle: { color: theme.text, fontFamily: theme.fontFamily },
      inactiveColor: theme.grid,
    },
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: theme.tooltip.background,
      borderColor: theme.tooltip.border,
      borderWidth: 1,
      padding: [6, 10],
      textStyle: { color: theme.tooltip.foreground, fontSize: 12, fontFamily: theme.fontFamily },
      extraCssText: "border-radius:8px;box-shadow:0 4px 16px rgb(0 0 0 / 0.12)",
      transitionDuration: reducedMotion ? 0 : 0.2,
      axisPointer: { type: "line", lineStyle: { color: theme.axis, width: 1 } },
      formatter,
    },
    xAxis: {
      type: "value",
      name: labels.epoch,
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: theme.text },
      min: "dataMin",
      max: "dataMax",
      minInterval: 1,
      axisLine: { lineStyle: { color: theme.axis } },
      axisTick: { lineStyle: { color: theme.axis } },
      axisLabel: { color: theme.text, formatter: (value: number) => labels.formatEpoch(value) },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.text, formatter: (value: number) => labels.formatValue(value) },
      splitLine: { lineStyle: { color: theme.grid, width: 1 } },
    },
    series: lines,
  };
}

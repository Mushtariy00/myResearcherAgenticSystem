import type { BarSeriesOption } from "echarts/charts";
import type { GridComponentOption, TooltipComponentOption } from "echarts/components";
import type { ComposeOption } from "echarts/core";
import { escapeHtml } from "@/components/shared/metrics-option";
import type { SpendDay } from "./dashboard-data";

/**
 * The spend chart's ECharts option (pure, so it is unit-tested without the chart runtime):
 * paid spend per UTC day as bars in the aurora colours, with the day's calls in the tooltip.
 */

export type SpendChartOption = ComposeOption<
  BarSeriesOption | GridComponentOption | TooltipComponentOption
>;

export type SpendChartTheme = {
  /** Canvas-ready colours (resolved from the Studio tokens). */
  barFrom: string;
  barTo: string;
  text: string;
  axis: string;
  grid: string;
  /** CSS colours for the HTML tooltip (variables are fine there). */
  tooltip: { background: string; foreground: string; border: string };
  fontFamily?: string;
};

export type SpendChartLabels = {
  paid: string;
  paidCalls: string;
  freeCalls: string;
  formatDay: (day: string) => string;
  formatUsd: (amount: number) => string;
  formatCount: (count: number) => string;
};

export function buildSpendOption({
  days,
  theme,
  labels,
  reducedMotion = false,
}: {
  days: readonly SpendDay[];
  theme: SpendChartTheme;
  labels: SpendChartLabels;
  reducedMotion?: boolean;
}): SpendChartOption {
  const formatter = (raw: unknown): string => {
    const params = (Array.isArray(raw) ? raw : [raw]) as { dataIndex?: number }[];
    const day = days[params[0]?.dataIndex ?? -1];
    if (!day) {
      return "";
    }
    const row = (label: string, value: string) =>
      `<tr><td style="padding:1px 12px 1px 0">${escapeHtml(label)}</td><td style="padding:1px 0;text-align:right;font-variant-numeric:tabular-nums;font-weight:600">${escapeHtml(value)}</td></tr>`;
    return `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(labels.formatDay(day.day))}</div><table style="border-collapse:collapse">${row(labels.paid, labels.formatUsd(day.paidUsd))}${row(labels.paidCalls, labels.formatCount(day.paidCalls))}${row(labels.freeCalls, labels.formatCount(day.freeCalls))}</table>`;
  };

  return {
    animation: !reducedMotion,
    animationDuration: 400,
    textStyle: { color: theme.text, fontFamily: theme.fontFamily },
    grid: { left: 4, right: 8, top: 12, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "shadow", shadowStyle: { color: theme.grid } },
      backgroundColor: theme.tooltip.background,
      borderColor: theme.tooltip.border,
      borderWidth: 1,
      padding: [6, 10],
      textStyle: { color: theme.tooltip.foreground, fontSize: 12, fontFamily: theme.fontFamily },
      extraCssText: "border-radius:10px;box-shadow:0 8px 24px rgb(0 0 0 / 0.18)",
      transitionDuration: reducedMotion ? 0 : 0.2,
      formatter,
    },
    xAxis: {
      type: "category",
      data: days.map((day) => labels.formatDay(day.day)),
      axisLine: { lineStyle: { color: theme.axis } },
      axisTick: { show: false },
      axisLabel: { color: theme.text, hideOverlap: true },
    },
    yAxis: {
      type: "value",
      minInterval: 0.01,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.text, formatter: (value: number) => labels.formatUsd(value) },
      splitLine: { lineStyle: { color: theme.grid, width: 1 } },
    },
    series: [
      {
        type: "bar",
        name: labels.paid,
        data: days.map((day) => day.paidUsd),
        barMaxWidth: 14,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: theme.barFrom },
              { offset: 1, color: theme.barTo },
            ],
          },
        },
        emphasis: { focus: "self" },
      },
    ],
  };
}

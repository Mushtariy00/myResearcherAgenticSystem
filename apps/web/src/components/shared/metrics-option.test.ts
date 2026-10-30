import { describe, expect, it } from "vitest";
import type { MetricSeries } from "@/client";
import {
  buildMetricsOption,
  type ChartTheme,
  escapeHtml,
  type MetricsChartLabels,
  metricSlots,
  seriesData,
} from "./metrics-option";

const theme: ChartTheme = {
  series: ["rgb(1, 1, 1)", "rgb(2, 2, 2)", "rgb(3, 3, 3)"],
  text: "rgb(10, 10, 10)",
  axis: "rgb(20, 20, 20)",
  grid: "rgb(30, 30, 30)",
  tooltip: {
    background: "var(--popover)",
    foreground: "var(--popover-foreground)",
    border: "var(--border)",
  },
  fontFamily: "Geist",
};

const labels: MetricsChartLabels = {
  epoch: "Epoch",
  split: { train: "Train", val: "Validation", test: "Test" },
  seriesName: (metric, split) => `${metric} (${split})`,
  higherIsBetter: "higher is better",
  lowerIsBetter: "lower is better",
  noValue: "No value",
  formatValue: (value) => value.toFixed(3),
  formatEpoch: (epoch) => String(epoch),
};

const series: MetricSeries[] = [
  {
    name: "loss",
    split: "train",
    higher_is_better: false,
    points: [
      { epoch: 1, value: 1.5 },
      { epoch: 0, value: 2.25 },
      { epoch: 2, value: null },
      { epoch: 3, value: 0.75 },
    ],
  },
  {
    name: "loss",
    split: "val",
    higher_is_better: false,
    points: [
      { epoch: 0, value: 2.5 },
      { epoch: 1, value: 1.75 },
    ],
  },
  {
    name: "delta1",
    split: "test",
    higher_is_better: true,
    points: [{ epoch: 3, value: 0.82 }],
  },
];

type LineOption = {
  id: string;
  name: string;
  data: [number, number | null][];
  showSymbol: boolean;
  connectNulls: boolean;
  lineStyle: { type: string; color: string };
};

function lines(option: ReturnType<typeof buildMetricsOption>): LineOption[] {
  return option.series as unknown as LineOption[];
}

describe("buildMetricsOption", () => {
  const option = buildMetricsOption({ series, theme, labels });

  it("draws one line per series, sorted by epoch, with missing values as gaps", () => {
    const [train, val, test] = lines(option);
    expect(lines(option)).toHaveLength(3);
    expect(train?.data).toEqual([
      [0, 2.25],
      [1, 1.5],
      [2, null],
      [3, 0.75],
    ]);
    expect(train?.connectNulls).toBe(false);
    expect(val?.name).toBe("loss (Validation)");
    expect(test?.id).toBe("delta1:test");
  });

  it("styles splits differently and colours by metric", () => {
    const [train, val, test] = lines(option);
    expect([train?.lineStyle.type, val?.lineStyle.type, test?.lineStyle.type]).toEqual([
      "solid",
      "dashed",
      "dotted",
    ]);
    expect(train?.lineStyle.color).toBe("rgb(1, 1, 1)");
    expect(val?.lineStyle.color).toBe("rgb(1, 1, 1)");
    expect(test?.lineStyle.color).toBe("rgb(2, 2, 2)");
    // A lone point between gaps is drawn as a marker so it stays visible.
    expect(test?.showSymbol).toBe(true);
  });

  it("keeps a metric's colour when a subset is shown", () => {
    const subset = buildMetricsOption({
      series: series.slice(2),
      theme,
      labels,
      metricOrder: ["loss", "delta1"],
    });
    expect(lines(subset)[0]?.lineStyle.color).toBe("rgb(2, 2, 2)");
    expect([...metricSlots(series, ["rmse"]).entries()]).toEqual([
      ["rmse", 0],
      ["loss", 1],
      ["delta1", 2],
    ]);
  });

  it("uses the theme colours and turns animation off for reduced motion", () => {
    expect(option.animation).toBe(true);
    expect(buildMetricsOption({ series, theme, labels, reducedMotion: true }).animation).toBe(
      false,
    );
    expect(option.textStyle).toMatchObject({ color: theme.text, fontFamily: "Geist" });
    expect(option.tooltip).toMatchObject({
      trigger: "axis",
      backgroundColor: "var(--popover)",
      borderColor: "var(--border)",
    });
    expect(option.yAxis).toMatchObject({ splitLine: { lineStyle: { color: theme.grid } } });
    expect(option.xAxis).toMatchObject({ type: "value", name: "Epoch", minInterval: 1 });
  });

  it("shows values, missing values and the better direction in the tooltip", () => {
    const tooltip = option.tooltip as { formatter: (params: unknown) => string };
    const html = tooltip.formatter([
      { seriesId: "loss:train", seriesName: "loss (Train)", marker: "<i></i>", value: [2, null] },
      { seriesId: "delta1:test", seriesName: "delta1 (Test)", marker: "<i></i>", value: [2, 0.8] },
    ]);
    expect(html).toContain("Epoch 2");
    expect(html).toContain("No value");
    expect(html).toContain("0.800");
    expect(html).toContain("↓ lower is better");
    expect(html).toContain("↑ higher is better");
  });

  it("escapes metric names in the tooltip", () => {
    const tooltip = option.tooltip as { formatter: (params: unknown) => string };
    const html = tooltip.formatter([
      { seriesId: "x", seriesName: '<img src=x onerror="alert(1)">', value: [0, 1] },
    ]);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
    expect(escapeHtml("a & b's")).toBe("a &amp; b&#39;s");
  });

  it("drops non-finite points", () => {
    expect(
      seriesData({
        name: "m",
        split: "val",
        higher_is_better: true,
        points: [
          { epoch: Number.NaN, value: 1 },
          { epoch: 1, value: Number.POSITIVE_INFINITY },
        ],
      }),
    ).toEqual([[1, null]]);
  });
});

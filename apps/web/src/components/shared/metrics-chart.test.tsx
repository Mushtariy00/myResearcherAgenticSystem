// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { MetricSeries } from "@/client";
import { MetricsChart } from "./metrics-chart";
import { renderWithIntl } from "./test-utils";

const { chart, init } = vi.hoisted(() => {
  const chart = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
  return { chart, init: vi.fn(() => chart) };
});

// ECharts draws on canvas, which jsdom lacks; the option itself is covered by metrics-option.test.
vi.mock("./metrics-chart-echarts", () => ({ init }));

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = (() =>
    null) as typeof HTMLCanvasElement.prototype.getContext;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const series: MetricSeries[] = [
  {
    name: "loss",
    split: "train",
    higher_is_better: false,
    points: [
      { epoch: 0, value: 2.2504 },
      { epoch: 1, value: null },
    ],
  },
  { name: "rmse", split: "val", higher_is_better: false, points: [{ epoch: 1, value: 1.4544 }] },
];

describe("MetricsChart", () => {
  it("has an accessible title and a data table with every value", () => {
    renderWithIntl(<MetricsChart series={series} title="Training curves" />);
    expect(screen.getByRole("figure", { name: "Training curves" })).toBeTruthy();
    const table = screen.getByRole("table", { name: "Training curves: values per epoch" });
    const rows = [...table.querySelectorAll("tbody tr")].map((row) =>
      [...row.children].map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ["0", "2.25", "No value"],
      ["1", "No value", "1.454"],
    ]);
    expect([...table.querySelectorAll("thead th")].map((cell) => cell.textContent)).toEqual([
      "Epoch",
      "loss (Train)",
      "rmse (Validation)",
    ]);
  });

  it("lets sighted users open the table", () => {
    renderWithIntl(<MetricsChart series={series} title="Training curves" />);
    const toggle = screen.getByRole("button", { name: "Show data table" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(
      screen.getByRole("button", { name: "Hide data table" }).getAttribute("aria-expanded"),
    ).toBe("true");
  });

  it("loads ECharts on demand and gives it the built option", async () => {
    renderWithIntl(<MetricsChart series={series} title="Training curves" />);
    await waitFor(() => expect(chart.setOption).toHaveBeenCalled());
    expect(init).toHaveBeenCalledWith(expect.any(HTMLElement), null, { renderer: "canvas" });
    const [option, settings] = chart.setOption.mock.calls[0] ?? [];
    expect(settings).toEqual({ notMerge: true });
    expect((option as { series: { id: string }[] }).series.map((line) => line.id)).toEqual([
      "loss:train",
      "rmse:val",
    ]);
    cleanup();
    expect(chart.dispose).toHaveBeenCalled();
  });

  it("says when nothing was recorded, without loading the chart", () => {
    renderWithIntl(
      <MetricsChart
        series={[
          {
            name: "loss",
            split: "val",
            higher_is_better: false,
            points: [{ epoch: 0, value: null }],
          },
        ]}
        title="Training curves"
      />,
    );
    expect(screen.getByText("No metrics were recorded.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(init).not.toHaveBeenCalled();
  });
});

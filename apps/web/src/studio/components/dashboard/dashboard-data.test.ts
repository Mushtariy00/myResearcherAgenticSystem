import { describe, expect, it } from "vitest";
import type { NotificationOut, RecentRunOut } from "@/client";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { awaitingPipeline, countPerDay, reviewQueue, summarizeRuns } from "./dashboard-data";
import { buildSpendOption } from "./spend-option";

const NOW = new Date("2026-10-30T03:00:00Z");

describe("countPerDay", () => {
  it("counts per UTC day, oldest first, and ignores dates outside the window", () => {
    expect(
      countPerDay(
        [
          "2026-10-30T01:00:00Z",
          "2026-10-29T23:59:59Z",
          "2026-10-29T00:00:00Z",
          "2026-10-24T12:00:00Z",
          "2026-10-31T00:00:00Z",
          "not a date",
        ],
        3,
        NOW,
      ),
    ).toEqual([0, 2, 1]);
  });
});

describe("summarizeRuns", () => {
  const run = (status: RecentRunOut["status"], created_at: string) =>
    ({ status, created_at }) as RecentRunOut;

  it("counts runs in progress, and runs started in the last two weeks", () => {
    const summary = summarizeRuns(
      [
        run("running", "2026-10-30T00:00:00Z"),
        run("paused_budget", "2026-10-28T00:00:00Z"),
        run("completed", "2026-10-01T00:00:00Z"),
        run("failed", "2026-10-29T00:00:00Z"),
      ],
      NOW,
    );
    expect(summary.active).toBe(2);
    expect(summary.running).toBe(1);
    expect(summary.startedPerDay).toHaveLength(14);
    expect(summary.startedInTrend).toBe(3);
  });
});

describe("the review queue", () => {
  it("draws the pipeline of a run waiting on a stage", () => {
    expect(
      awaitingPipeline(["literature", "method", "coding", "experiment"], "coding").map(
        (node) => node.status,
      ),
    ).toEqual(["approved", "approved", "output_ready", "pending", "skipped"]);
  });

  it("puts what expires first, then the longest-waiting, from approval notifications only", () => {
    const base = {
      read: false,
      project_id: "p1",
      stage: "method",
      params: { topic: "T", project: "P", stage: "method" },
    };
    const notifications: NotificationOut[] = [
      {
        ...base,
        key: "approval:a",
        kind: "approval_needed",
        created_at: "2026-10-29T00:00:00Z",
        run_id: "r-a",
      },
      {
        ...base,
        key: "approval:b",
        kind: "approval_needed",
        created_at: "2026-10-20T00:00:00Z",
        run_id: "r-b",
      },
      {
        ...base,
        key: "approval:c",
        kind: "approval_needed",
        created_at: "2026-10-25T00:00:00Z",
        run_id: "r-c",
      },
      {
        ...base,
        key: "approval.expiring:a",
        kind: "approval_expiring",
        created_at: "2026-10-29T00:00:00Z",
        run_id: "r-a",
      },
      {
        ...base,
        key: "run.finished:r-d",
        kind: "run_completed",
        created_at: "2026-10-29T00:00:00Z",
        run_id: "r-d",
      },
    ];
    const runs = [
      {
        id: "r-b",
        topic: "B",
        project_name: "P",
        config: { ...RUN_CONFIG_DEFAULTS, stages: ["literature", "method"] },
      },
    ] as RecentRunOut[];
    const queue = reviewQueue(notifications, runs);
    expect(queue.map((item) => item.runId)).toEqual(["r-a", "r-b", "r-c"]);
    expect(queue[0]?.expiring).toBe(true);
    // The run's own stages when it is among the recent runs, all five otherwise.
    expect(queue[1]?.nodes.map((node) => node.status)).toEqual([
      "approved",
      "output_ready",
      "skipped",
      "skipped",
      "skipped",
    ]);
    expect(queue[2]?.nodes.filter((node) => node.status === "pending")).toHaveLength(3);
  });
});

describe("the spend chart option", () => {
  it("puts each day's paid spend on a bar, with no animation for reduced motion", () => {
    const option = buildSpendOption({
      days: [
        { day: "2026-10-29", paidUsd: 1.5, paidCalls: 3, freeCalls: 1 },
        { day: "2026-10-30", paidUsd: 0, paidCalls: 0, freeCalls: 9 },
      ],
      theme: {
        barFrom: "#8b5cf6",
        barTo: "#6366f1",
        text: "#555",
        axis: "#999",
        grid: "#eee",
        tooltip: { background: "white", foreground: "black", border: "gray" },
      },
      labels: {
        paid: "Paid spend",
        paidCalls: "Paid calls",
        freeCalls: "Free calls",
        formatDay: (day) => day.slice(5),
        formatUsd: (amount) => `$${amount.toFixed(2)}`,
        formatCount: String,
      },
      reducedMotion: true,
    });
    expect(option.animation).toBe(false);
    const series = Array.isArray(option.series) ? option.series[0] : option.series;
    expect(series?.data).toEqual([1.5, 0]);
    const tooltip = Array.isArray(option.tooltip) ? option.tooltip[0] : option.tooltip;
    const formatter = tooltip?.formatter as (params: unknown) => string;
    const html = formatter([{ dataIndex: 1 }]);
    expect(html).toContain("10-30");
    expect(html).toContain("Free calls");
    expect(html).toContain(">9<");
  });
});

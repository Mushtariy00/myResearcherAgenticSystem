import { describe, expect, it } from "vitest";
import type { RunStatus, Stage, StageRunOut, StageStatus } from "@/client";
import { buildTimeline, isTerminalRunStatus, retryableStages, STAGE_ORDER } from "./timeline";

let counter = 0;

function stageRun(
  stage: string,
  status: StageStatus,
  attempt = 1,
  extra: Partial<StageRunOut> = {},
): StageRunOut {
  counter += 1;
  return {
    id: `00000000-0000-0000-0000-${String(counter).padStart(12, "0")}`,
    stage,
    attempt,
    status,
    feedback: null,
    error: null,
    started_at: `2026-10-30T00:00:${String(counter).padStart(2, "0")}Z`,
    finished_at: null,
    outputs: [],
    ...extra,
  };
}

const statuses = (entries: ReturnType<typeof buildTimeline>) => entries.map((e) => e.status);

describe("buildTimeline", () => {
  it("shows all five stages as waiting before anything ran", () => {
    const entries = buildTimeline(STAGE_ORDER, [], "queued");
    expect(entries.map((e) => e.stage)).toEqual([...STAGE_ORDER]);
    expect(statuses(entries)).toEqual(["pending", "pending", "pending", "pending", "pending"]);
    expect(entries.some((e) => e.current)).toBe(false);
  });

  it("marks the running stage as current", () => {
    const entries = buildTimeline(
      STAGE_ORDER,
      [stageRun("literature", "approved"), stageRun("method", "running")],
      "running",
    );
    expect(statuses(entries)).toEqual(["approved", "running", "pending", "pending", "pending"]);
    expect(entries.filter((e) => e.current).map((e) => e.stage)).toEqual(["method"]);
  });

  it("uses the latest attempt after changes were requested", () => {
    const entries = buildTimeline(
      STAGE_ORDER,
      [stageRun("literature", "output_ready", 2), stageRun("literature", "changes_requested", 1)],
      "awaiting_approval",
    );
    expect(entries[0]).toMatchObject({ status: "output_ready", attempts: 2, current: true });
    expect(entries[0]?.latest?.attempt).toBe(2);
  });

  it("closes unfinished stages and skips the rest when a run is cancelled", () => {
    const entries = buildTimeline(
      STAGE_ORDER,
      [stageRun("literature", "approved"), stageRun("method", "running")],
      "cancelled",
    );
    expect(statuses(entries)).toEqual(["approved", "cancelled", "skipped", "skipped", "skipped"]);
    expect(entries.some((e) => e.current)).toBe(false);
  });

  it("shows a failed run's stuck stage as failed", () => {
    const entries = buildTimeline(STAGE_ORDER, [stageRun("literature", "running")], "failed");
    expect(statuses(entries)).toEqual(["failed", "skipped", "skipped", "skipped", "skipped"]);
  });

  it("keeps the recorded outcome for stages that already finished", () => {
    const entries = buildTimeline(
      STAGE_ORDER,
      [stageRun("literature", "approved"), stageRun("method", "rejected")],
      "rejected",
    );
    expect(statuses(entries)).toEqual(["approved", "rejected", "skipped", "skipped", "skipped"]);
  });

  it("lists completed runs as approved end to end", () => {
    const entries = buildTimeline(
      STAGE_ORDER,
      STAGE_ORDER.map((stage) => stageRun(stage, "approved")),
      "completed",
    );
    expect(statuses(entries)).toEqual(Array(5).fill("approved"));
  });

  it("appends stages the API knows but the order list does not", () => {
    const entries = buildTimeline(["literature"], [stageRun("review", "running")], "running");
    expect(entries.map((e) => e.stage)).toEqual(["literature", "review"]);
  });
});

describe("isTerminalRunStatus", () => {
  it("knows which run statuses are final", () => {
    expect(isTerminalRunStatus("completed")).toBe(true);
    expect(isTerminalRunStatus("cancelled")).toBe(true);
    expect(isTerminalRunStatus("awaiting_approval")).toBe(false);
    expect(isTerminalRunStatus("paused_budget")).toBe(false);
    expect(isTerminalRunStatus(undefined)).toBe(false);
  });
});

describe("retryableStages", () => {
  const run = (status: RunStatus, reached: string[], stages: Stage[] = [...STAGE_ORDER]) => ({
    status,
    config: {
      year_from: 2018,
      year_to: 2026,
      sources: ["arxiv" as const],
      max_papers: 20,
      stages,
      dataset: "nyu2",
    },
    stages: reached.map((stage) => stageRun(stage, "approved")),
  });

  it("offers every reached stage of a finished run, in pipeline order", () => {
    expect(retryableStages(run("completed", ["writing", "literature", "method"]))).toEqual([
      "literature",
      "method",
      "writing",
    ]);
    for (const status of ["failed", "rejected", "cancelled"] as const) {
      expect(retryableStages(run(status, ["literature", "method"]))).toEqual([
        "literature",
        "method",
      ]);
    }
  });

  it("offers nothing while the run is still going", () => {
    for (const status of ["queued", "running", "awaiting_approval", "paused_budget"] as const) {
      expect(retryableStages(run(status, ["literature"]))).toEqual([]);
    }
  });

  it("skips stages the run never reached or no longer includes", () => {
    expect(
      retryableStages(run("failed", ["literature", "method", "review"], ["literature"])),
    ).toEqual(["literature"]);
    expect(retryableStages(run("cancelled", []))).toEqual([]);
  });
});

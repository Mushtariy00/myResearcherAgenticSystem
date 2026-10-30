import { describe, expect, it } from "vitest";
import {
  affectsRunDetail,
  lastSeq,
  mergeEvents,
  parseRunEvent,
  type RunEvent,
  stageDetailChanges,
  summarizeEvent,
  summarizeSpend,
} from "./run-events";

function event(seq: number, type = "log", payload: Record<string, unknown> = {}): RunEvent {
  return {
    seq,
    type,
    payload,
    created_at: `2026-10-30T00:00:${String(seq % 60).padStart(2, "0")}Z`,
  };
}

describe("parseRunEvent", () => {
  it("reads the JSON the API sends in each SSE message", () => {
    const data = JSON.stringify({
      seq: 7,
      type: "stage.started",
      payload: { stage: "literature" },
      created_at: "2026-10-30T01:02:03+00:00",
    });
    expect(parseRunEvent(data)).toEqual({
      seq: 7,
      type: "stage.started",
      payload: { stage: "literature" },
      created_at: "2026-10-30T01:02:03+00:00",
    });
  });

  it("ignores malformed messages instead of throwing", () => {
    expect(parseRunEvent("not json")).toBeNull();
    expect(parseRunEvent("{}")).toBeNull();
    expect(parseRunEvent(JSON.stringify({ seq: "1", type: "log" }))).toBeNull();
    expect(parseRunEvent(JSON.stringify({ seq: -1, type: "log" }))).toBeNull();
    expect(parseRunEvent(JSON.stringify({ seq: 1.5, type: "log" }))).toBeNull();
    expect(parseRunEvent("null")).toBeNull();
  });

  it("treats a missing or non-object payload as empty", () => {
    expect(
      parseRunEvent(JSON.stringify({ seq: 1, type: "log", payload: [1, 2] }))?.payload,
    ).toEqual({});
    expect(parseRunEvent(JSON.stringify({ seq: 1, type: "log" }))?.payload).toEqual({});
  });
});

describe("mergeEvents", () => {
  it("appends new events in seq order", () => {
    const merged = mergeEvents([event(1), event(2)], [event(4), event(3)]);
    expect(merged.map((e) => e.seq)).toEqual([1, 2, 3, 4]);
  });

  it("drops events already seen (replay after a reconnect or remount)", () => {
    const first = event(2, "log", { message: "first copy" });
    const merged = mergeEvents(
      [event(1), first],
      [event(2, "log", { message: "replayed" }), event(3)],
    );
    expect(merged.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(merged[1]).toBe(first);
  });

  it("de-duplicates within one incoming batch", () => {
    expect(mergeEvents([], [event(5), event(5), event(6)]).map((e) => e.seq)).toEqual([5, 6]);
  });

  it("returns the same array when nothing is new, so React can skip a render", () => {
    const current = [event(1), event(2)];
    expect(mergeEvents(current, [event(2), event(1)])).toBe(current);
    expect(mergeEvents(current, [])).toBe(current);
  });

  it("keeps only the newest events when over the limit", () => {
    const merged = mergeEvents([event(1), event(2), event(3)], [event(4), event(5)], 3);
    expect(merged.map((e) => e.seq)).toEqual([3, 4, 5]);
  });
});

describe("lastSeq", () => {
  it("is the highest seq, or 0 before any event", () => {
    expect(lastSeq([])).toBe(0);
    expect(lastSeq(mergeEvents([], [event(9), event(3)]))).toBe(9);
  });
});

describe("affectsRunDetail", () => {
  it("refetches the run after stage and status events only", () => {
    for (const type of [
      "run.status",
      "stage.started",
      "stage.output_ready",
      "stage.decided",
      "stage.failed",
    ]) {
      expect(affectsRunDetail(type)).toBe(true);
    }
    for (const type of ["run.created", "llm.call", "log"]) {
      expect(affectsRunDetail(type)).toBe(false);
    }
  });
});

describe("summarizeEvent", () => {
  it("extracts the fields shown for known event types", () => {
    expect(
      summarizeEvent(event(1, "stage.decided", { stage: "method", decision: "approve" })),
    ).toEqual({ kind: "stageDecided", stage: "method", decision: "approve" });
    expect(summarizeEvent(event(2, "run.status", { status: "failed", error: "boom" }))).toEqual({
      kind: "runStatus",
      status: "failed",
      error: "boom",
    });
    expect(summarizeEvent(event(3, "llm.call", { model: "m", tier: "free" }))).toEqual({
      kind: "llmCall",
      model: "m",
      tier: "free",
      costUsd: null,
      switchedToFree: false,
      replayed: false,
    });
  });

  it("reads the gateway's call details (cost as a decimal string, fallback to free)", () => {
    const call = event(4, "llm.call", {
      tier: "free",
      model: "fake/research-planner:free",
      stage: "literature",
      cost_usd: "0",
      replayed: false,
      switched_to_free: true,
    });
    expect(summarizeEvent(call)).toMatchObject({ costUsd: null, switchedToFree: true });
    const paid = event(5, "llm.call", { tier: "paid", model: "x", cost_usd: "0.0125" });
    expect(summarizeEvent(paid)).toMatchObject({ tier: "paid", costUsd: 0.0125 });
  });

  it("flags degraded outputs and repeated attempts", () => {
    const ready = event(6, "stage.output_ready", {
      stage: "literature",
      attempt: 1,
      degraded: true,
    });
    expect(summarizeEvent(ready)).toEqual({
      kind: "stageOutputReady",
      stage: "literature",
      degraded: true,
    });
    const retry = event(7, "stage.started", { stage: "method", attempt: 2 });
    expect(summarizeEvent(retry)).toEqual({ kind: "stageStarted", stage: "method", attempt: 2 });
  });

  it("falls back to JSON text for unknown or incomplete events", () => {
    expect(summarizeEvent(event(1, "gpu.queued", { position: 2 }))).toEqual({
      kind: "raw",
      text: '{"position":2}',
    });
    expect(summarizeEvent(event(2, "stage.started", {}))).toEqual({ kind: "raw", text: "" });
  });

  it("never interprets markup in payloads (it stays plain text)", () => {
    const summary = summarizeEvent(event(1, "log", { message: "<img src=x onerror=alert(1)>" }));
    expect(summary).toEqual({ kind: "log", message: "<img src=x onerror=alert(1)>" });
  });
});

/** An llm.call payload as apps/worker/src/agentic_worker/events.py writes it. */
function llmCall(seq: number, stage: string, call: Record<string, unknown>): RunEvent {
  return event(seq, "llm.call", {
    stage,
    model: "fake/model",
    tier: "paid",
    cost_usd: "0",
    switched_to_free: false,
    replayed: false,
    ...call,
  });
}

describe("summarizeSpend", () => {
  it("adds up the gateway's decimal strings exactly, per stage", () => {
    const spend = summarizeSpend([
      event(1, "stage.started", { stage: "literature", attempt: 1 }),
      llmCall(2, "literature", { cost_usd: "0.1" }),
      llmCall(3, "literature", { cost_usd: "0.2" }),
      llmCall(4, "method", { cost_usd: "0.0125" }),
      event(5, "log", { message: "cost_usd: 99" }),
    ]);
    expect(spend.totalUsd).toBe(0.3125);
    expect(spend.byStage).toEqual({ literature: 0.3, method: 0.0125 });
    expect(spend).toMatchObject({ calls: 3, paidCalls: 3, freeCalls: 0, lastSeq: 4 });
  });

  it("counts free calls and calls without a cost as nothing", () => {
    const spend = summarizeSpend([
      llmCall(1, "literature", { tier: "free", model: "fake/model:free" }),
      // str(None) when the gateway answer had no cost.
      llmCall(2, "literature", { cost_usd: "None" }),
      llmCall(3, "literature", { cost_usd: "-1" }),
    ]);
    expect(spend).toMatchObject({ totalUsd: 0, calls: 3, paidCalls: 2, freeCalls: 1 });
    expect(spend.byStage).toEqual({ literature: 0 });
  });

  it("counts a crash replay's cost once (its original call never reached the log)", () => {
    const spend = summarizeSpend([
      llmCall(7, "literature", { cost_usd: "0.004", replayed: true }),
      llmCall(8, "literature", { cost_usd: "0.006" }),
    ]);
    expect(spend).toMatchObject({ totalUsd: 0.01, calls: 2, replayedCalls: 1 });
  });

  it("notices when the gateway switched to free models", () => {
    expect(summarizeSpend([llmCall(1, "method", {})]).switchedToFree).toBe(false);
    const switched = llmCall(2, "method", { tier: "free", switched_to_free: true });
    expect(summarizeSpend([llmCall(1, "method", {}), switched]).switchedToFree).toBe(true);
  });

  it("is all zeros before the first call", () => {
    expect(summarizeSpend([])).toEqual({
      totalUsd: 0,
      byStage: {},
      calls: 0,
      paidCalls: 0,
      freeCalls: 0,
      replayedCalls: 0,
      switchedToFree: false,
      lastSeq: 0,
    });
  });
});

describe("stageDetailChanges", () => {
  const events = [
    event(1, "run.created", { topic: "Depth" }),
    event(2, "stage.started", { stage: "literature", attempt: 1 }),
    event(3, "llm.call", { stage: "literature", tier: "free" }),
    event(4, "log", { stage: "literature", message: "Searching arXiv" }),
    event(5, "stage.output_ready", { stage: "literature", attempt: 1 }),
    event(6, "run.status", { status: "awaiting_approval" }),
    event(7, "stage.decided", { stage: "literature", decision: "approve" }),
    event(8, "stage.started", { stage: "method", attempt: 1 }),
  ];

  it("names the stages whose events arrived after the given seq", () => {
    expect(stageDetailChanges(events, 0)).toEqual({
      stages: ["literature", "method"],
      all: false,
      lastSeq: 8,
    });
    expect(stageDetailChanges(events, 7)).toEqual({ stages: ["method"], all: false, lastSeq: 8 });
    expect(stageDetailChanges(events, 8)).toEqual({ stages: [], all: false, lastSeq: 8 });
  });

  it("ignores calls and log lines, which do not change a stage's detail", () => {
    expect(stageDetailChanges(events.slice(2, 4), 0)).toEqual({
      stages: [],
      all: false,
      lastSeq: 4,
    });
  });

  it("follows retries to the stage the run restarts at", () => {
    const retried = [
      event(20, "run.status", { status: "running", retry_stage: "method" }),
      event(21, "stage.invalidated", { stage: "coding", attempt: 1, retry_stage: "method" }),
      event(22, "run.retried", { stage: "method", requested_stage: "method" }),
    ];
    expect(stageDetailChanges(retried, 19)).toEqual({
      stages: ["coding", "method"],
      all: false,
      lastSeq: 22,
    });
  });

  it("marks every stage when the run finishes (a cancel closes attempts silently)", () => {
    const cancelled = [event(30, "run.status", { status: "cancelled", error: null })];
    expect(stageDetailChanges(cancelled, 0)).toMatchObject({ all: true, lastSeq: 30 });
    const bogus = [event(31, "run.status", { status: "exploded" })];
    expect(stageDetailChanges(bogus, 0).all).toBe(false);
  });
});

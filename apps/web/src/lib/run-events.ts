/** Live run events from `GET /api/v1/runs/{id}/events` (SSE), merged and de-duplicated by seq. */

import { isRunStatus } from "./labels";
import { isTerminalRunStatus } from "./timeline";

export type RunEvent = {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

/** How many events the log keeps in memory (the oldest are dropped first). */
export const MAX_EVENTS = 2000;

/** Parses one SSE `data:` line; anything malformed is ignored instead of breaking the stream. */
export function parseRunEvent(data: string): RunEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object") {
    return null;
  }
  const { seq, type, payload, created_at } = value as Record<string, unknown>;
  if (typeof seq !== "number" || !Number.isInteger(seq) || seq < 0 || typeof type !== "string") {
    return null;
  }
  return {
    seq,
    type,
    payload:
      payload && typeof payload === "object" && !Array.isArray(payload)
        ? (payload as Record<string, unknown>)
        : {},
    created_at: typeof created_at === "string" ? created_at : "",
  };
}

/**
 * Adds `incoming` to `current`, keeping one event per seq in ascending order (replays after a
 * reconnect or a remount repeat events). Returns `current` itself when nothing is new, so React
 * can skip the re-render.
 */
export function mergeEvents(
  current: readonly RunEvent[],
  incoming: readonly RunEvent[],
  limit: number = MAX_EVENTS,
): readonly RunEvent[] {
  if (incoming.length === 0) {
    return current;
  }
  const bySeq = new Map<number, RunEvent>();
  for (const event of current) {
    bySeq.set(event.seq, event);
  }
  let added = false;
  for (const event of incoming) {
    if (!bySeq.has(event.seq)) {
      bySeq.set(event.seq, event);
      added = true;
    }
  }
  if (!added) {
    return current;
  }
  const merged = [...bySeq.values()].sort((a, b) => a.seq - b.seq);
  return merged.length > limit ? merged.slice(merged.length - limit) : merged;
}

/** Highest seq seen so far (0 before the first event), used as `?after=` on a fresh connection. */
export function lastSeq(events: readonly RunEvent[]): number {
  return events.length === 0 ? 0 : (events[events.length - 1]?.seq ?? 0);
}

/** Events after which the run detail (timeline, awaiting output) must be fetched again. */
export function affectsRunDetail(type: string): boolean {
  return type === "run.status" || type.startsWith("stage.");
}

export type StageDetailChanges = {
  /** Stages whose detail (attempts, versions, decisions) the events changed. */
  stages: string[];
  /** The run finished: every stage may have changed (open attempts close without stage events). */
  all: boolean;
  /** The highest seq looked at (`afterSeq` when there was nothing newer). */
  lastSeq: number;
};

/**
 * Which stage details the events after `afterSeq` changed, so their queries can be fetched
 * again: each `stage.*` event names its stage, and `run.retried` the stage the run restarts at.
 * A final `run.status` (completed, rejected, failed, cancelled) marks every stage.
 */
export function stageDetailChanges(
  events: readonly RunEvent[],
  afterSeq: number,
): StageDetailChanges {
  const stages = new Set<string>();
  let all = false;
  let lastSeq = afterSeq;
  for (const event of events) {
    if (event.seq <= afterSeq) {
      continue;
    }
    lastSeq = Math.max(lastSeq, event.seq);
    const stage = text(event.payload.stage);
    if ((event.type.startsWith("stage.") || event.type === "run.retried") && stage) {
      stages.add(stage);
    } else if (event.type === "run.status") {
      const status = text(event.payload.status);
      all ||= status !== null && isRunStatus(status) && isTerminalRunStatus(status);
    }
  }
  return { stages: [...stages], all, lastSeq };
}

/** A run's LLM spend so far, from its `llm.call` events (see `summarizeSpend`). */
export type RunSpend = {
  /** USD summed over every call (free calls cost 0). */
  totalUsd: number;
  /** USD per stage, for the stages that made calls. */
  byStage: Readonly<Record<string, number>>;
  calls: number;
  paidCalls: number;
  freeCalls: number;
  /** Calls answered from the gateway's journal after a crash (their cost is counted once). */
  replayedCalls: number;
  /** The gateway fell back to free models at least once (the owner's budget ran out). */
  switchedToFree: boolean;
  /** Seq of the newest `llm.call` event, 0 before the first. */
  lastSeq: number;
};

/** Costs are summed in billionths of a dollar, so decimal strings add up exactly. */
const NANO_USD = 1_000_000_000;

/**
 * Sums a run's LLM spend from its `llm.call` events. The worker writes one per gateway answer
 * (apps/worker/src/agentic_worker/events.py `llm_call`): `stage`, `model`, `tier`, `cost_usd`
 * as the gateway's Decimal in a string ("0.0125"; "0" for free calls; "None" when it had no
 * cost), `switched_to_free` and `replayed`.
 *
 * Replayed calls are counted: a replay answers a retried activity from the gateway's journal
 * with the original call's cost, and the original attempt's events were never stored (they are
 * committed together with the stage output), so the replay is the only event for that money.
 * This is a live figure: calls of a failed or cancelled attempt never reach the log, and the
 * gateway's journal (`GET /usage`) stays the authority.
 */
export function summarizeSpend(events: readonly RunEvent[]): RunSpend {
  let total = 0;
  const byStage = new Map<string, number>();
  const spend = {
    calls: 0,
    paidCalls: 0,
    freeCalls: 0,
    replayedCalls: 0,
    switchedToFree: false,
    lastSeq: 0,
  };
  for (const event of events) {
    if (event.type !== "llm.call") {
      continue;
    }
    const p = event.payload;
    const nano = Math.round((positiveNumber(p.cost_usd) ?? 0) * NANO_USD);
    const stage = text(p.stage);
    total += nano;
    if (stage) {
      byStage.set(stage, (byStage.get(stage) ?? 0) + nano);
    }
    spend.calls += 1;
    if (p.tier === "paid") {
      spend.paidCalls += 1;
    } else if (p.tier === "free") {
      spend.freeCalls += 1;
    }
    if (p.replayed === true) {
      spend.replayedCalls += 1;
    }
    spend.switchedToFree ||= p.switched_to_free === true;
    spend.lastSeq = Math.max(spend.lastSeq, event.seq);
  }
  return {
    ...spend,
    totalUsd: total / NANO_USD,
    byStage: Object.fromEntries([...byStage].map(([stage, nano]) => [stage, nano / NANO_USD])),
  };
}

export type EventSummary =
  | { kind: "runCreated"; topic: string }
  | { kind: "runStatus"; status: string; error: string | null }
  | { kind: "stageStarted"; stage: string; attempt: number }
  | { kind: "stageOutputReady"; stage: string; degraded: boolean }
  | { kind: "stageDecided"; stage: string; decision: string }
  | { kind: "stageFailed"; stage: string; error: string | null }
  | {
      kind: "llmCall";
      model: string;
      tier: string;
      /** Paid cost in USD when above zero. */
      costUsd: number | null;
      /** The gateway fell back to free models (budget used up). */
      switchedToFree: boolean;
      /** A crash replay reused a response that was already paid for. */
      replayed: boolean;
    }
  | { kind: "log"; message: string }
  | { kind: "raw"; text: string };

function text(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function positiveNumber(value: unknown): number | null {
  const amount = typeof value === "number" ? value : Number.parseFloat(String(value ?? ""));
  return Number.isFinite(amount) && amount > 0 ? amount : null;
}

/** Picks the fields the log shows for known event types; anything else is shown as JSON text. */
export function summarizeEvent(event: RunEvent): EventSummary {
  const p = event.payload;
  switch (event.type) {
    case "run.created":
      return { kind: "runCreated", topic: text(p.topic) ?? "" };
    case "run.status":
      if (text(p.status)) {
        return { kind: "runStatus", status: text(p.status) ?? "", error: text(p.error) };
      }
      break;
    case "stage.started":
      if (text(p.stage)) {
        const attempt = typeof p.attempt === "number" && p.attempt > 0 ? p.attempt : 1;
        return { kind: "stageStarted", stage: text(p.stage) ?? "", attempt };
      }
      break;
    case "stage.output_ready":
      if (text(p.stage)) {
        return {
          kind: "stageOutputReady",
          stage: text(p.stage) ?? "",
          degraded: p.degraded === true,
        };
      }
      break;
    case "stage.decided":
      if (text(p.stage) && text(p.decision)) {
        return {
          kind: "stageDecided",
          stage: text(p.stage) ?? "",
          decision: text(p.decision) ?? "",
        };
      }
      break;
    case "stage.failed":
      if (text(p.stage)) {
        return { kind: "stageFailed", stage: text(p.stage) ?? "", error: text(p.error) };
      }
      break;
    case "llm.call":
      return {
        kind: "llmCall",
        model: text(p.model) ?? "?",
        tier: text(p.tier) ?? "?",
        costUsd: positiveNumber(p.cost_usd),
        switchedToFree: p.switched_to_free === true,
        replayed: p.replayed === true,
      };
    case "log":
      if (text(p.message)) {
        return { kind: "log", message: text(p.message) ?? "" };
      }
      break;
  }
  return { kind: "raw", text: Object.keys(p).length === 0 ? "" : JSON.stringify(p) };
}

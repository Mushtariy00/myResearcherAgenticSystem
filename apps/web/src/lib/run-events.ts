/** Live run events from `GET /api/v1/runs/{id}/events` (SSE), merged and de-duplicated by seq. */

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

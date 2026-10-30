import type { RunOut, RunStatus } from "@/client";
import { toAmount } from "@/lib/format";

/** Status filters of the runs table: groups of run statuses. */
export const RUN_FILTERS = ["all", "active", "review", "completed", "stopped"] as const;
export type RunFilter = (typeof RUN_FILTERS)[number];

const FILTER_STATUSES: Record<Exclude<RunFilter, "all">, readonly RunStatus[]> = {
  active: ["queued", "running", "paused_budget"],
  review: ["awaiting_approval"],
  completed: ["completed"],
  stopped: ["failed", "rejected", "cancelled"],
};

export function isRunFilter(value: unknown): value is RunFilter {
  return typeof value === "string" && (RUN_FILTERS as readonly string[]).includes(value);
}

export const RUN_SORT_KEYS = ["topic", "status", "policy", "cap", "created"] as const;
export type RunSortKey = (typeof RUN_SORT_KEYS)[number];
export type RunSort = { key: RunSortKey; desc: boolean };

export const DEFAULT_RUN_SORT: RunSort = { key: "created", desc: true };

/** Statuses in the order a person looks at them: what needs them first, what is over last. */
const STATUS_ORDER: Record<RunStatus, number> = {
  awaiting_approval: 0,
  running: 1,
  queued: 2,
  paused_budget: 3,
  failed: 4,
  rejected: 5,
  cancelled: 6,
  completed: 7,
};

/** Runs whose topic contains every word of `query` (any case) and whose status fits `filter`. */
export function filterRuns(runs: readonly RunOut[], query: string, filter: RunFilter): RunOut[] {
  const words = query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const statuses = filter === "all" ? null : new Set(FILTER_STATUSES[filter]);
  return runs.filter((run) => {
    if (statuses && !statuses.has(run.status)) {
      return false;
    }
    const topic = run.topic.toLocaleLowerCase();
    return words.every((word) => topic.includes(word));
  });
}

function compare(a: RunOut, b: RunOut, key: RunSortKey, locale: string): number {
  switch (key) {
    case "topic":
      return a.topic.localeCompare(b.topic, locale, { sensitivity: "base", numeric: true });
    case "status":
      return STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    case "policy":
      return a.llm_policy.localeCompare(b.llm_policy);
    case "cap": {
      // Runs without a cap sort as the highest (they may spend up to the budget).
      const left =
        a.budget_cap_usd === null ? Number.POSITIVE_INFINITY : toAmount(a.budget_cap_usd);
      const right =
        b.budget_cap_usd === null ? Number.POSITIVE_INFINITY : toAmount(b.budget_cap_usd);
      return left === right ? 0 : left < right ? -1 : 1;
    }
    case "created":
      return a.created_at.localeCompare(b.created_at);
  }
}

/** A sorted copy; ties keep the newest run first. */
export function sortRuns(runs: readonly RunOut[], sort: RunSort, locale = "en"): RunOut[] {
  const direction = sort.desc ? -1 : 1;
  return [...runs].sort(
    (a, b) =>
      compare(a, b, sort.key, locale) * direction || b.created_at.localeCompare(a.created_at),
  );
}

/** The next sort after clicking a column: the same column flips, another starts in its order. */
export function nextSort(current: RunSort, key: RunSortKey): RunSort {
  if (current.key === key) {
    return { key, desc: !current.desc };
  }
  return { key, desc: key === "created" || key === "cap" };
}

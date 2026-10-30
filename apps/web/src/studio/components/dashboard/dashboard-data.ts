import type { NotificationOut, RecentRunOut, RunStatus, UsageOut } from "@/client";
import { percentUsed, toAmount } from "@/lib/format";
import { STAGE_ORDER, type TimelineStatus } from "@/lib/timeline";
import type { PipelineNode } from "@/studio/components/pipeline-graph";

/**
 * What the Studio dashboard shows, worked out from the shared hooks' data (pure functions, so
 * they are tested without rendering). Days are UTC days, as the usage journal counts them.
 */

const DAY_MS = 86_400_000;

/** Days of the run and review sparklines; the spend figures cover the usage window (30 days). */
export const TREND_DAYS = 14;

/** Still in progress: queued, running, waiting for a decision, or paused on the lab balance. */
const ACTIVE_STATUSES = new Set<RunStatus>([
  "queued",
  "running",
  "awaiting_approval",
  "paused_budget",
]);

export function isActiveRun(status: RunStatus): boolean {
  return ACTIVE_STATUSES.has(status);
}

function utcDay(value: string | Date): number {
  return Math.floor(new Date(value).getTime() / DAY_MS);
}

/** How many of `dates` fall on each of the last `days` UTC days: oldest first, today last. */
export function countPerDay(dates: readonly string[], days: number, now: Date): number[] {
  const today = utcDay(now);
  const counts = Array.from({ length: days }, () => 0);
  for (const date of dates) {
    const offset = today - utcDay(date);
    if (Number.isFinite(offset) && offset >= 0 && offset < days) {
      const index = days - 1 - offset;
      counts[index] = (counts[index] ?? 0) + 1;
    }
  }
  return counts;
}

export type RunSummary = {
  /** Runs in progress among the newest runs of the caller's projects. */
  active: number;
  running: number;
  /** Runs started on each of the last TREND_DAYS days. */
  startedPerDay: number[];
  startedInTrend: number;
};

export function summarizeRuns(runs: readonly RecentRunOut[], now: Date): RunSummary {
  const startedPerDay = countPerDay(
    runs.map((run) => run.created_at),
    TREND_DAYS,
    now,
  );
  return {
    active: runs.filter((run) => isActiveRun(run.status)).length,
    running: runs.filter((run) => run.status === "running").length,
    startedPerDay,
    startedInTrend: startedPerDay.reduce((sum, count) => sum + count, 0),
  };
}

export type SpendDay = { day: string; paidUsd: number; paidCalls: number; freeCalls: number };

export type UsageSummary = {
  /** Paid spend this UTC month, the monthly budget and what is left of it. */
  spentThisMonth: number;
  budget: number;
  remaining: number;
  /** Share of the budget used, 0..100. */
  percentUsed: number;
  freeCallsToday: number;
  paidCallsToday: number;
  /** Every day of the usage window, oldest first. */
  days: SpendDay[];
  paidInWindow: number;
};

function utcDate(now: Date): string {
  return now.toISOString().slice(0, 10);
}

export function summarizeUsage(usage: UsageOut, now: Date): UsageSummary {
  const days = [...usage.by_day]
    .sort((a, b) => a.day.localeCompare(b.day))
    .map((day) => ({
      day: day.day.slice(0, 10),
      paidUsd: toAmount(day.paid_usd),
      paidCalls: day.paid_calls,
      freeCalls: day.free_calls,
    }));
  const today = days.find((day) => day.day === utcDate(now));
  const budget = toAmount(usage.budget.monthly_usd);
  const spent = toAmount(usage.budget.spent_usd);
  return {
    spentThisMonth: spent,
    budget,
    remaining: Math.max(0, toAmount(usage.budget.remaining_usd)),
    percentUsed: percentUsed(spent, budget),
    freeCallsToday: today?.freeCalls ?? 0,
    paidCallsToday: today?.paidCalls ?? 0,
    days,
    paidInWindow: toAmount(usage.totals.paid_usd),
  };
}

/**
 * The pipeline of a run that waits for a decision on `awaiting`: the stages before it were
 * approved (a stage only starts from the approved output of the one before), the stage itself
 * needs review, later stages wait, and stages the run was not configured for never run.
 */
export function awaitingPipeline(stages: readonly string[], awaiting: string): PipelineNode[] {
  const at = (STAGE_ORDER as readonly string[]).indexOf(awaiting);
  return STAGE_ORDER.map((stage, index) => {
    let status: TimelineStatus = "pending";
    if (!stages.includes(stage)) {
      status = "skipped";
    } else if (at >= 0 && index < at) {
      status = "approved";
    } else if (index === at) {
      status = "output_ready";
    }
    return { stage, status };
  });
}

export type ReviewItem = {
  /** The notification key (one per waiting output). */
  key: string;
  runId: string;
  projectId: string | null;
  topic: string;
  project: string;
  stage: string;
  /** When the output became ready. */
  readyAt: string;
  /** The decision is due within a day (the run is cancelled if nobody decides). */
  expiring: boolean;
  nodes: PipelineNode[];
};

function outputOf(key: string): string {
  return key.slice(key.indexOf(":") + 1);
}

function text(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/**
 * Outputs waiting for a decision the caller may make: the API derives an `approval_needed`
 * notification for exactly those (its can-steer rule). Expiring ones come first, then the
 * longest-waiting. Each gets its run's pipeline (the run's stages come from the recent runs;
 * a run outside that list shows all five).
 */
export function reviewQueue(
  notifications: readonly NotificationOut[],
  runs: readonly RecentRunOut[],
): ReviewItem[] {
  const expiring = new Set(
    notifications
      .filter((notification) => notification.kind === "approval_expiring")
      .map((notification) => outputOf(notification.key)),
  );
  const runsById = new Map(runs.map((run) => [run.id, run]));
  const items: ReviewItem[] = [];
  for (const notification of notifications) {
    if (notification.kind !== "approval_needed" || !notification.run_id) {
      continue;
    }
    const run = runsById.get(notification.run_id);
    const stage = text(notification.params.stage ?? notification.stage);
    items.push({
      key: notification.key,
      runId: notification.run_id,
      projectId: notification.project_id,
      topic: text(notification.params.topic) || run?.topic || "",
      project: text(notification.params.project) || run?.project_name || "",
      stage,
      readyAt: notification.created_at,
      expiring: expiring.has(outputOf(notification.key)),
      nodes: awaitingPipeline(run?.config.stages ?? STAGE_ORDER, stage),
    });
  }
  return items.sort(
    (a, b) => Number(b.expiring) - Number(a.expiring) || a.readyAt.localeCompare(b.readyAt),
  );
}

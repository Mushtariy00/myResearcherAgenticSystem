import type { RunStatus, StageRunOut, StageStatus } from "@/client";

/** Pipeline order (also served by `GET /api/v1/stages`; this is the fallback while it loads). */
export const STAGE_ORDER = ["literature", "method", "coding", "experiment", "writing"] as const;

const TERMINAL_RUN_STATUSES = new Set<RunStatus>(["completed", "rejected", "failed", "cancelled"]);
const UNFINISHED_STAGE_STATUSES = new Set<StageStatus>(["pending", "running", "output_ready"]);

/** Stage statuses from the API, plus `skipped` for stages a finished run never reached. */
export type TimelineStatus = StageStatus | "skipped";

export type TimelineEntry = {
  stage: string;
  status: TimelineStatus;
  /** Attempts so far (a "request changes" decision starts a new attempt). */
  attempts: number;
  latest: StageRunOut | undefined;
  /** The stage the run is working on or waiting for a decision on. */
  current: boolean;
};

export function isTerminalRunStatus(status: RunStatus | undefined): boolean {
  return status !== undefined && TERMINAL_RUN_STATUSES.has(status);
}

function latestAttempt(attempts: StageRunOut[]): StageRunOut | undefined {
  let latest: StageRunOut | undefined;
  for (const attempt of attempts) {
    if (
      !latest ||
      attempt.attempt > latest.attempt ||
      (attempt.attempt === latest.attempt && (attempt.started_at ?? "") > (latest.started_at ?? ""))
    ) {
      latest = attempt;
    }
  }
  return latest;
}

/**
 * One entry per pipeline stage, in order. Each shows its latest attempt's status. When a run
 * has finished, stages it never reached are `skipped`, and an attempt the API still reports as
 * unfinished takes the run's outcome (cancelled or failed) so the timeline never looks stuck.
 */
export function buildTimeline(
  stages: readonly string[],
  stageRuns: readonly StageRunOut[],
  runStatus: RunStatus,
): TimelineEntry[] {
  const byStage = new Map<string, StageRunOut[]>();
  for (const stageRun of stageRuns) {
    const list = byStage.get(stageRun.stage) ?? [];
    list.push(stageRun);
    byStage.set(stageRun.stage, list);
  }
  const order = [...stages, ...[...byStage.keys()].filter((stage) => !stages.includes(stage))];
  const finished = TERMINAL_RUN_STATUSES.has(runStatus);

  return order.map((stage) => {
    const attempts = byStage.get(stage) ?? [];
    const latest = latestAttempt(attempts);
    let status: TimelineStatus = latest?.status ?? "pending";
    if (finished) {
      if (!latest) {
        status = "skipped";
      } else if (UNFINISHED_STAGE_STATUSES.has(latest.status)) {
        if (runStatus === "cancelled") {
          status = "cancelled";
        } else if (runStatus === "failed") {
          status = "failed";
        }
      }
    }
    const current = !finished && (status === "running" || status === "output_ready");
    return { stage, status, attempts: attempts.length, latest, current };
  });
}

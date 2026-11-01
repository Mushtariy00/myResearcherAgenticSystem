import type { RunOut, RunStatus, Stage, StageRunOut, StageStatus } from "@/client";

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
  /** The run was started without this stage, so it never runs (and shows as `skipped`). */
  excluded?: boolean;
};

export function isTerminalRunStatus(status: RunStatus | undefined): boolean {
  return status !== undefined && TERMINAL_RUN_STATUSES.has(status);
}

/**
 * The stages `POST /runs/{id}/retry?stage=` accepts, in pipeline order: the run has finished
 * (completed, rejected, failed or cancelled), and the stage is one of the run's configured
 * stages and has at least one attempt. Whether the caller may retry is `can_steer`'s job.
 */
export function retryableStages(
  run: Pick<RunOut, "status" | "config"> & { stages: readonly Pick<StageRunOut, "stage">[] },
): Stage[] {
  if (!TERMINAL_RUN_STATUSES.has(run.status)) {
    return [];
  }
  const reached = new Set(run.stages.map((stageRun) => stageRun.stage));
  return run.config.stages.filter((stage) => reached.has(stage));
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
 * Given the run's own stages (`included`), the others are `skipped` and `excluded` from the
 * start, not waiting.
 */
export function buildTimeline(
  stages: readonly string[],
  stageRuns: readonly StageRunOut[],
  runStatus: RunStatus,
  included?: readonly string[],
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
    const excluded = !latest && included !== undefined && !included.includes(stage);
    let status: TimelineStatus = latest?.status ?? (excluded ? "skipped" : "pending");
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
    const entry: TimelineEntry = { stage, status, attempts: attempts.length, latest, current };
    return excluded ? { ...entry, excluded } : entry;
  });
}

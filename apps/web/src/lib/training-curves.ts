/**
 * Live training curves for every interface: while the experiment stage trains on the GPU, the
 * executor writes one `experiment.epoch` run event per finished epoch, and the stage view draws
 * them as the metric series its output will store once the training has ended.
 */
import type { MetricSeries } from "@/client";
import { type EpochMetrics, type EpochRecord, epochRecord, type RunEvent } from "./run-events";

/** The stage that trains on the GPU, whose view draws the live curves. */
export const TRAINING_STAGE = "experiment";

/**
 * The harness's metrics, in its order (sandbox/pytorch/harness/tasks.py); lower is better for
 * every one. The stored series hold these and no others (apps/worker experiment/output.py).
 */
export const HARNESS_METRICS = ["loss", "rmse", "mae", "abs_rel"] as const;

/** Validation before training, as the worker stores them (the headline is the first non-loss). */
const SPLITS = ["val", "train"] as const;

/**
 * Epochs beyond this are ignored. The worker plans at most 50 (ARP_EXPERIMENT_EPOCHS); the cap
 * only keeps a bogus epoch number from filling a chart with millions of empty points.
 */
export const MAX_LIVE_EPOCHS = 1000;

/** The training job the curves follow, and what it reported so far. */
export type LiveTraining = {
  stage: string;
  jobId: string;
  /** Epochs reported so far. */
  epochs: number;
  /** The newest epoch reported (the last event received). */
  latest: EpochRecord;
  /**
   * For each harness metric, validation then training, a point per epoch from 0 to the newest
   * one: null where the metric was not measured or that epoch's event never arrived.
   */
  series: MetricSeries[];
};

/** The events the live curves are drawn from: epochs, and the stage starts that reset them. */
export function isTrainingEvent(event: RunEvent): boolean {
  return event.type === "experiment.epoch" || event.type === "stage.started";
}

/**
 * The metric series of one job's epochs, as the stage output will store them (the worker's
 * `metric_series`). A later record of an epoch replaces an earlier one.
 */
export function epochSeries(records: readonly EpochRecord[]): MetricSeries[] {
  const byEpoch = new Map<number, EpochRecord>();
  for (const record of records) {
    if (record.epoch < MAX_LIVE_EPOCHS) {
      byEpoch.set(record.epoch, record);
    }
  }
  if (byEpoch.size === 0) {
    return [];
  }
  const epochs = Math.max(...byEpoch.keys()) + 1;
  return HARNESS_METRICS.flatMap((name) =>
    SPLITS.map(
      (split): MetricSeries => ({
        name,
        split,
        higher_is_better: false,
        points: Array.from({ length: epochs }, (_, epoch) => ({
          epoch,
          value: byEpoch.get(epoch)?.[split][name] ?? null,
        })),
      }),
    ),
  );
}

/**
 * The live curves of `stage`'s training: the `experiment.epoch` events of kind "train" since
 * the stage's latest `stage.started` (its current attempt), of the newest job among them.
 * `events` must be in seq order (as useRunEvents keeps them). Null before the first epoch.
 */
export function liveTraining(
  events: readonly RunEvent[],
  stage: string = TRAINING_STAGE,
): LiveTraining | null {
  let jobId: string | null = null;
  let records: EpochRecord[] = [];
  for (const event of events) {
    if (event.type === "stage.started") {
      if (event.payload.stage === stage) {
        jobId = null;
        records = [];
      }
      continue;
    }
    if (event.type !== "experiment.epoch") {
      continue;
    }
    const record = epochRecord(event.payload);
    if (record?.kind !== "train" || record.stage !== stage) {
      continue;
    }
    if (record.jobId !== jobId) {
      // A newer job of the attempt: its curves start over.
      jobId = record.jobId;
      records = [];
    }
    if (record.epoch < MAX_LIVE_EPOCHS) {
      records.push(record);
    }
  }
  const latest = records.at(-1);
  if (jobId === null || !latest) {
    return null;
  }
  return {
    stage,
    jobId,
    epochs: new Set(records.map((record) => record.epoch)).size,
    latest,
    series: epochSeries(records),
  };
}

/** The reading a log line shows for an epoch: one metric of one split. */
export type EpochReading = {
  split: "val" | "train";
  metric: string;
  /** Null when the metric was not measured. */
  value: number | null;
  /** The same metric on the training split, when the reading is a validation one. */
  train: number | null;
};

/** The harness's metrics first (in its order), then any others by name. */
function metricOrder(metrics: EpochMetrics): string[] {
  const known: readonly string[] = HARNESS_METRICS;
  const names = Object.keys(metrics);
  return [
    ...known.filter((name) => names.includes(name)),
    ...names.filter((name) => !known.includes(name)).sort(),
  ];
}

/**
 * What an epoch's log line says: validation, else training; the first metric that is not a
 * loss and was measured (RMSE for the harness), else the loss, else the first metric with no
 * value (it reads "not measured"). Null when the epoch reported no metric at all.
 */
export function epochReading(record: EpochRecord): EpochReading | null {
  for (const split of SPLITS) {
    const metrics = record[split];
    const names = metricOrder(metrics);
    if (names.length === 0) {
      continue;
    }
    const candidates = [
      ...names.filter((name) => name !== "loss"),
      ...names.filter((name) => name === "loss"),
    ];
    const metric = candidates.find((name) => metrics[name] !== null) ?? candidates[0] ?? "";
    return {
      split,
      metric,
      value: metrics[metric] ?? null,
      train: split === "val" ? (record.train[metric] ?? null) : null,
    };
  }
  return null;
}

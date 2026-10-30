import { describe, expect, it } from "vitest";
import type { MetricSeries } from "@/client";
import { type EpochRecord, epochRecord, type RunEvent } from "./run-events";
import {
  epochReading,
  epochSeries,
  isTrainingEvent,
  liveTraining,
  MAX_LIVE_EPOCHS,
} from "./training-curves";

let seq = 0;
function event(type: string, payload: Record<string, unknown>): RunEvent {
  seq += 1;
  return { seq, type, payload, created_at: "2026-10-31T01:00:00Z" };
}

/** A split's metrics as the harness reports them (null: not measured). */
function depth(
  loss: number | null,
  rmse: number | null,
  mae: number | null,
  absRel: number | null,
) {
  return { loss, rmse, mae, abs_rel: absRel };
}

/** An experiment.epoch event as the executor writes it (agentic_executor `_report_epoch`). */
function epoch(
  number: number,
  val: Record<string, number | null>,
  train: Record<string, number | null> = {},
  job = { stage: "experiment", job_id: "job-1", kind: "train", ordinal: 1 },
): RunEvent {
  return event("experiment.epoch", { ...job, epoch: number, train, val });
}

function record(number: number, val: Record<string, number | null>): EpochRecord {
  return {
    stage: "experiment",
    jobId: "job-1",
    kind: "train",
    ordinal: 1,
    epoch: number,
    train: {},
    val,
  };
}

/** The points of one series, as [epoch, value] pairs. */
function points(series: readonly MetricSeries[], name: string, split: string) {
  const found = series.find((entry) => entry.name === name && entry.split === split);
  return found?.points.map((point) => [point.epoch, point.value]);
}

describe("epochSeries", () => {
  it("has validation then training for each harness metric, as the stored output will", () => {
    const series = epochSeries([
      { ...record(0, depth(0.9, 1.2, 0.8, 0.4)), train: depth(1.1, 1.4, 1.0, 0.5) },
      { ...record(1, depth(0.7, 0.9, 0.6, 0.3)), train: depth(0.8, 1.0, 0.7, 0.35) },
    ]);
    expect(series.map((entry) => `${entry.name}:${entry.split}`)).toEqual([
      "loss:val",
      "loss:train",
      "rmse:val",
      "rmse:train",
      "mae:val",
      "mae:train",
      "abs_rel:val",
      "abs_rel:train",
    ]);
    expect(series.every((entry) => entry.higher_is_better === false)).toBe(true);
    expect(points(series, "rmse", "val")).toEqual([
      [0, 1.2],
      [1, 0.9],
    ]);
    expect(points(series, "rmse", "train")).toEqual([
      [0, 1.4],
      [1, 1.0],
    ]);
  });

  it("leaves a gap (null, never 0) for a metric not measured or an epoch that never arrived", () => {
    const series = epochSeries([
      record(0, depth(0.9, null, 0.8, 0.4)),
      record(2, depth(0.6, 0.7, 0.5, 0.2)),
    ]);
    expect(points(series, "rmse", "val")).toEqual([
      [0, null],
      [1, null],
      [2, 0.7],
    ]);
    // The training split reported nothing.
    expect(points(series, "loss", "train")).toEqual([
      [0, null],
      [1, null],
      [2, null],
    ]);
  });

  it("takes a later record of an epoch over an earlier one, and ignores other metrics", () => {
    const series = epochSeries([
      record(0, { loss: 0.9, delta1: 0.7 }),
      record(0, { loss: 0.8, delta1: 0.75 }),
    ]);
    expect(points(series, "loss", "val")).toEqual([[0, 0.8]]);
    expect(series.some((entry) => entry.name === "delta1")).toBe(false);
  });

  it("is empty without a record, and ignores absurd epoch numbers", () => {
    expect(epochSeries([])).toEqual([]);
    expect(epochSeries([record(MAX_LIVE_EPOCHS, { loss: 1 })])).toEqual([]);
  });
});

describe("liveTraining", () => {
  const started = (attempt: number) => event("stage.started", { stage: "experiment", attempt });

  it("draws the current attempt's training epochs, and counts them", () => {
    const training = liveTraining([
      started(1),
      event("log", { stage: "experiment", code: "experiment.planned", params: {} }),
      epoch(0, depth(0.9, 1.2, 0.8, 0.4), depth(1.0, 1.3, 0.9, 0.45)),
      event("llm.call", { stage: "writing" }),
      epoch(1, depth(0.7, 0.9, 0.6, 0.3), depth(0.8, 1.0, 0.7, 0.35)),
    ]);
    expect(training).toMatchObject({ stage: "experiment", jobId: "job-1", epochs: 2 });
    expect(training?.latest.epoch).toBe(1);
    expect(points(training?.series ?? [], "rmse", "val")).toEqual([
      [0, 1.2],
      [1, 0.9],
    ]);
  });

  it("is null before the first epoch", () => {
    expect(liveTraining([])).toBeNull();
    expect(liveTraining([started(1)])).toBeNull();
  });

  it("leaves out smoke tests, other stages and events it cannot read", () => {
    const smoke = { stage: "coding", job_id: "smoke-1", kind: "smoke", ordinal: 2 };
    expect(
      liveTraining([
        epoch(0, depth(3.1, 3.2, 3.0, 1.1), {}, smoke),
        epoch(0, { loss: 1 }, {}, { stage: "coding", job_id: "x", kind: "train", ordinal: 1 }),
        event("experiment.epoch", { stage: "experiment", job_id: "job-1", kind: "train" }),
        event("experiment.epoch", { stage: "experiment", kind: "train", epoch: -1 }),
        event("experiment.epoch", { stage: "experiment", kind: "train", epoch: 0.5 }),
      ]),
    ).toBeNull();
  });

  it("starts over when the stage starts again, and follows the newest job", () => {
    const retried = liveTraining([
      started(1),
      epoch(0, { loss: 0.9 }),
      epoch(1, { loss: 0.8 }),
      started(2),
    ]);
    expect(retried).toBeNull();

    const second = { stage: "experiment", job_id: "job-2", kind: "train", ordinal: 1 };
    const newer = liveTraining([
      started(2),
      epoch(0, { loss: 0.9 }),
      epoch(0, { loss: 0.5 }, {}, second),
    ]);
    expect(newer).toMatchObject({ jobId: "job-2", epochs: 1 });
    expect(points(newer?.series ?? [], "loss", "val")).toEqual([[0, 0.5]]);
  });

  it("keeps following the stage when another stage starts", () => {
    const training = liveTraining([
      started(1),
      epoch(0, { loss: 0.9 }),
      event("stage.started", { stage: "writing", attempt: 1 }),
    ]);
    expect(training?.epochs).toBe(1);
  });

  it("reads the events it needs from the log", () => {
    expect(isTrainingEvent(epoch(0, {}))).toBe(true);
    expect(isTrainingEvent(started(1))).toBe(true);
    expect(isTrainingEvent(event("log", { stage: "experiment" }))).toBe(false);
    expect(isTrainingEvent(event("llm.call", {}))).toBe(false);
  });
});

describe("epochReading", () => {
  const read = (val: Record<string, unknown>, train: Record<string, unknown> = {}) => {
    const parsed = epochRecord({ epoch: 2, kind: "train", job_id: "j", val, train });
    if (!parsed) {
      throw new Error("not an epoch");
    }
    return epochReading(parsed);
  };

  it("reads the first validation metric that is not a loss, with its training value", () => {
    expect(read(depth(0.43, 0.512, 0.38, 0.12), depth(0.31, 0.498, 0.35, 0.11))).toEqual({
      split: "val",
      metric: "rmse",
      value: 0.512,
      train: 0.498,
    });
  });

  it("falls back to a measured metric, then the loss, then 'not measured'", () => {
    expect(read(depth(0.43, null, 0.38, null))).toMatchObject({ metric: "mae", value: 0.38 });
    expect(read(depth(0.43, null, null, null))).toMatchObject({ metric: "loss", value: 0.43 });
    expect(read(depth(null, null, null, null))).toMatchObject({ metric: "rmse", value: null });
    expect(read({ delta1: 0.81 })).toMatchObject({ metric: "delta1", value: 0.81 });
  });

  it("reads the training split when validation reported nothing, and nothing without metrics", () => {
    expect(read({}, depth(0.31, 0.498, 0.35, 0.11))).toEqual({
      split: "train",
      metric: "rmse",
      value: 0.498,
      train: null,
    });
    expect(read({}, {})).toBeNull();
  });

  it("never reads a value that is not a finite number", () => {
    expect(read({ rmse: "0.5", mae: Number.NaN, loss: 0.4 })).toMatchObject({
      metric: "loss",
      value: 0.4,
    });
  });
});

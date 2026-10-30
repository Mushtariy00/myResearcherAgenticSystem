import type { GpuQueueOut } from "@/client";

/**
 * What the GPU widgets of both interfaces show in place of the readings (`GET /gpu/queue`):
 * - `offline`: the executor's heartbeat is stale, so it is not running and queued jobs wait for
 *   it; any reading it left behind is out of date, so none is shown;
 * - `none`: the executor runs but has not reported a reading yet;
 * - `live`: the readings (one this GPU or driver does not give is null: show a dash, never 0).
 * A demo queue's readings are generated, with no executor behind them: they show as `live`.
 */
export type GpuReadings = "offline" | "none" | "live";

export function gpuReadings(
  queue: Pick<GpuQueueOut, "gpu" | "executor_alive" | "demo">,
): GpuReadings {
  if (!queue.executor_alive && !queue.demo) {
    return "offline";
  }
  return queue.gpu ? "live" : "none";
}

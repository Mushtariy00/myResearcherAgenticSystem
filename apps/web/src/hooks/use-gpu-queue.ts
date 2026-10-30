"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { GpuQueueOut } from "@/client";
import { getGpuQueueOptions } from "@/client/@tanstack/react-query.gen";
import { POLL_INTERVALS, pollWhileVisible } from "@/lib/polling";

/**
 * The lab GPU: the executor's latest readings, the running jobs (each a smoke test or a
 * training, `kind`), the queue in order and the caller's place (`my_position`: 0 running, n-th
 * waiting, null none). Refreshes every 5 s while the page is visible, and at once when the user
 * comes back to it. `gpu` is null and `executor_alive` false while the executor reports nothing:
 * `gpuReadings` (lib/gpu.ts) says what to show instead.
 */
export function useGpuQueue(): UseQueryResult<GpuQueueOut, Error> {
  return useQuery({
    ...getGpuQueueOptions(),
    staleTime: 2_000,
    ...pollWhileVisible(POLL_INTERVALS.gpuQueue),
  });
}

"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { GpuQueueOut } from "@/client";
import { getGpuQueueOptions } from "@/client/@tanstack/react-query.gen";
import { POLL_INTERVALS, pollWhileVisible } from "@/lib/polling";

/**
 * The lab GPU: live readings, the running job, the queue in order and the caller's place
 * (`my_position`: 0 running, n-th waiting, null none). Refreshes every 5 s while the page is
 * visible, and at once when the user comes back to it.
 */
export function useGpuQueue(): UseQueryResult<GpuQueueOut, Error> {
  return useQuery({
    ...getGpuQueueOptions(),
    staleTime: 2_000,
    ...pollWhileVisible(POLL_INTERVALS.gpuQueue),
  });
}

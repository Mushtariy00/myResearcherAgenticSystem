"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { SystemHealthOut } from "@/client";
import { getSystemHealthOptions } from "@/client/@tanstack/react-query.gen";
import { POLL_INTERVALS, pollWhileVisible } from "@/lib/polling";

/**
 * Admin: Postgres, Valkey, Temporal, the gateway and the workers, each `ok`, `degraded`, `down`
 * or `unknown` with its probe latency; `status` is the worst of them. Refreshes every 15 s while
 * the page is visible. Lab admins only (403 otherwise, and then it stops polling).
 */
export function useSystemHealth(): UseQueryResult<SystemHealthOut, Error> {
  return useQuery({
    ...getSystemHealthOptions(),
    staleTime: 5_000,
    ...pollWhileVisible(POLL_INTERVALS.systemHealth),
  });
}

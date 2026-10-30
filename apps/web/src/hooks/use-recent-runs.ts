"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { ListRecentRunsData, ListRecentRunsError, RecentRunOut, RunStatus } from "@/client";
import { listRecentRunsOptions } from "@/client/@tanstack/react-query.gen";

export const RECENT_RUNS_LIMIT = { default: 20, max: 100 } as const;

/**
 * The newest runs across the caller's projects (every project for lab admins), newest first,
 * with each run's project name: the dashboard list. `limit` is kept within 1..100; `status`
 * keeps one status (e.g. "awaiting_approval" for a review queue). Creating a run refreshes it.
 */
export function useRecentRuns(
  limit: number = RECENT_RUNS_LIMIT.default,
  status?: RunStatus | null,
): UseQueryResult<RecentRunOut[], ListRecentRunsError> {
  const size = Number.isFinite(limit)
    ? Math.min(RECENT_RUNS_LIMIT.max, Math.max(1, Math.floor(limit)))
    : RECENT_RUNS_LIMIT.default;
  const query: NonNullable<ListRecentRunsData["query"]> = { limit: size };
  if (status) {
    query.status = status;
  }
  return useQuery({ ...listRecentRunsOptions({ query }), staleTime: 15_000 });
}

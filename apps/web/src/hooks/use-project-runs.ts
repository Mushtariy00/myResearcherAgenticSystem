"use client";

import {
  type InfiniteData,
  type UseInfiniteQueryResult,
  useInfiniteQuery,
} from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import type { ListRunsError, RunOut } from "@/client";
import { listRunsInfiniteQueryKey } from "@/client/@tanstack/react-query.gen";
import { listRuns } from "@/client/sdk.gen";
import { isTerminalRunStatus } from "@/lib/timeline";

/** Runs per page (`limit`); the API answers newest first, and a shorter page is the last one. */
export const RUNS_PAGE_SIZE = 50;

/** While a run on screen is still going, the loaded pages are refreshed this often. */
const ACTIVE_REFRESH_MS = 15_000;

export type ProjectRuns = {
  query: UseInfiniteQueryResult<InfiniteData<RunOut[], string | null>, ListRunsError>;
  /** Every run loaded so far, newest first; undefined until the first page arrives. */
  runs: RunOut[] | undefined;
  /** Older runs exist beyond what is loaded. */
  hasMore: boolean;
  /** Loads the next page (`before` the oldest run loaded). */
  loadMore: () => void;
  loadingMore: boolean;
};

/**
 * A project's runs, one page at a time (`GET /projects/{id}/runs?before=&limit=`), for the run
 * lists of both interfaces. Every loaded page refreshes while one of its runs is in progress.
 */
export function useProjectRuns(projectId: string, pageSize: number = RUNS_PAGE_SIZE): ProjectRuns {
  const query = useInfiniteQuery<
    RunOut[],
    ListRunsError,
    InfiniteData<RunOut[], string | null>,
    ReturnType<typeof listRunsInfiniteQueryKey>,
    string | null
  >({
    queryKey: listRunsInfiniteQueryKey({
      path: { project_id: projectId },
      query: { limit: pageSize },
    }),
    queryFn: async ({ pageParam, signal }) => {
      const { data } = await listRuns({
        path: { project_id: projectId },
        query: pageParam === null ? { limit: pageSize } : { before: pageParam, limit: pageSize },
        signal,
        throwOnError: true,
      });
      return data;
    },
    initialPageParam: null,
    getNextPageParam: (lastPage) =>
      lastPage.length < pageSize ? undefined : (lastPage.at(-1)?.id ?? undefined),
    refetchInterval: (current) =>
      current.state.data?.pages.some((page) => page.some((run) => !isTerminalRunStatus(run.status)))
        ? ACTIVE_REFRESH_MS
        : false,
  });
  const runs = useMemo(() => query.data?.pages.flat(), [query.data]);
  const { fetchNextPage, hasNextPage, isFetchingNextPage } = query;
  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);
  return { query, runs, hasMore: hasNextPage, loadMore, loadingMore: isFetchingNextPage };
}

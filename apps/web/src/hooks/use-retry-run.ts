"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { retryRunMutation } from "@/client/@tanstack/react-query.gen";
import { invalidateRunQueries } from "@/hooks/use-run-view";
import { type ApiError, toApiError } from "@/lib/api-error";

export type RetryRunCallbacks = {
  /** The API accepted the retry (202): the run restarts at `stage` in a new execution. */
  onRetried?: (runId: string, stage: string) => void;
  /**
   * The retry was refused: 409 `run.not_retryable` (the run has not finished, or another retry
   * started), 409 `stage.not_reached`, 403 `permission.denied`, 503 `orchestrator.unavailable`.
   */
  onError?: (error: ApiError, runId: string, stage: string) => void;
};

export type RetryRun = {
  /** Runs a finished run again from `stage` (offer the run's `retryableStages`). */
  retry: (runId: string, stage: string) => void;
  /** Like `retry`, as a promise; it rejects with the ApiError. */
  retryAsync: (runId: string, stage: string) => Promise<void>;
  /** A retry is being sent (until the run detail has been refetched). */
  pending: boolean;
  pendingRunId: string | null;
  pendingStage: string | null;
  /** The last failure, until the next retry or `reset`. */
  error: ApiError | null;
  reset: () => void;
};

/**
 * Retrying a finished run from one stage (`POST /runs/{id}/retry?stage=`). The workflow keeps
 * the approved outputs before `stage` and invalidates the outputs from it on, so the run, its
 * stage details, artifacts and the run lists are refetched afterwards. Not bound to one run, so
 * a list can offer it per row.
 */
export function useRetryRun(callbacks: RetryRunCallbacks = {}): RetryRun {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    ...retryRunMutation(),
    onSuccess: (_data, variables) => {
      callbacks.onRetried?.(variables.path.run_id, variables.query.stage);
    },
    onError: (error, variables) => {
      callbacks.onError?.(toApiError(error), variables.path.run_id, variables.query.stage);
    },
    onSettled: (_data, _error, variables) =>
      invalidateRunQueries(queryClient, variables.path.run_id),
  });
  const { mutate, mutateAsync, reset } = mutation;
  const retry = useCallback(
    (runId: string, stage: string) => mutate({ path: { run_id: runId }, query: { stage } }),
    [mutate],
  );
  const retryAsync = useCallback(
    async (runId: string, stage: string) => {
      await mutateAsync({ path: { run_id: runId }, query: { stage } });
    },
    [mutateAsync],
  );
  const pending = mutation.isPending;
  return {
    retry,
    retryAsync,
    pending,
    pendingRunId: pending ? (mutation.variables?.path.run_id ?? null) : null,
    pendingStage: pending ? (mutation.variables?.query.stage ?? null) : null,
    error: mutation.error ? toApiError(mutation.error) : null,
    reset,
  };
}

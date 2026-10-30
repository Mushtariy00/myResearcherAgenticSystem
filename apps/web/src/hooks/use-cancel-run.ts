"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { cancelRunMutation } from "@/client/@tanstack/react-query.gen";
import { invalidateRunQueries } from "@/hooks/use-run-view";
import { type ApiError, toApiError } from "@/lib/api-error";

/** The run had already finished: there was nothing to cancel, which is not a failure. */
const ALREADY_FINISHED = "run.already_finished";

export type CancelRunCallbacks = {
  /** The API accepted the cancel (202); the run reaches "cancelled" shortly. */
  onCancelled?: (runId: string) => void;
  /** 409 `run.already_finished`. Without this callback it goes to `onError`. */
  onAlreadyFinished?: (runId: string, error: ApiError) => void;
  /** 403 `permission.denied`, 503 `orchestrator.unavailable`, network errors... */
  onError?: (error: ApiError, runId: string) => void;
};

export type CancelRun = {
  cancel: (runId: string) => void;
  /** Like `cancel`, as a promise; it rejects with the ApiError (also for an already finished run). */
  cancelAsync: (runId: string) => Promise<void>;
  /** A cancel is being sent (until the run detail has been refetched). */
  pending: boolean;
  pendingRunId: string | null;
  /** The last failure, until the next cancel or `reset`. */
  error: ApiError | null;
  /** The last cancel found the run already finished (`error` is that 409). */
  alreadyFinished: boolean;
  reset: () => void;
};

/**
 * Cancelling a run (`POST /runs/{id}/cancel`): stops work in progress, including a GPU job.
 * Afterwards the run, its stage details, the run lists and the GPU queue are refetched. Not bound
 * to one run, so a list can offer it per row.
 */
export function useCancelRun(callbacks: CancelRunCallbacks = {}): CancelRun {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    ...cancelRunMutation(),
    onSuccess: (_data, variables) => {
      callbacks.onCancelled?.(variables.path.run_id);
    },
    onError: (error, variables) => {
      const apiError = toApiError(error);
      if (apiError.code === ALREADY_FINISHED && callbacks.onAlreadyFinished) {
        callbacks.onAlreadyFinished(variables.path.run_id, apiError);
      } else {
        callbacks.onError?.(apiError, variables.path.run_id);
      }
    },
    onSettled: (_data, _error, variables) =>
      invalidateRunQueries(queryClient, variables.path.run_id, { gpu: true }),
  });
  const { mutate, mutateAsync, reset } = mutation;
  const cancel = useCallback((runId: string) => mutate({ path: { run_id: runId } }), [mutate]);
  const cancelAsync = useCallback(
    async (runId: string) => {
      await mutateAsync({ path: { run_id: runId } });
    },
    [mutateAsync],
  );
  const pending = mutation.isPending;
  const error = mutation.error ? toApiError(mutation.error) : null;
  return {
    cancel,
    cancelAsync,
    pending,
    pendingRunId: pending ? (mutation.variables?.path.run_id ?? null) : null,
    error,
    alreadyFinished: error?.code === ALREADY_FINISHED,
    reset,
  };
}

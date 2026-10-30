"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import type { Decision, RunDetail, StageOutputOut } from "@/client";
import { client } from "@/client/client.gen";
import { decideStage } from "@/client/sdk.gen";
import { invalidateRunQueries } from "@/hooks/use-run-view";
import { APPROVAL_CONFLICT_CODES, ApiError, toApiError } from "@/lib/api-error";

/** The API's limit for a review comment (`DecisionIn.comment`); use it as the input's maxLength. */
export const MAX_COMMENT_LENGTH = 5000;

/** What the hook reads from the run detail. */
export type ApprovalRun = Pick<
  RunDetail,
  "id" | "awaiting" | "awaiting_stage" | "can_steer" | "stages" | "max_attempts" | "attempts_left"
>;

/** Which attempt the output under review is: "Attempt 2 of 3", or "Attempt 2" when unknown. */
export type ReviewAttempt = {
  /** Its place in this execution of the run (a retry starts a new one), or the stage's count. */
  number: number;
  /** Attempts the execution allows (`max_attempts`); null when the API does not say. */
  of: number | null;
};

/** Where an approve-with-edits failed the stage's schema (422 `decision.invalid_edit`). */
export type InvalidEdit = {
  /**
   * Path of the first error, as field names and list indexes (`["proposals", 0, "risk"]`).
   * "*" stands for a key the API does not echo back; empty when the whole output is wrong.
   */
  loc: readonly (string | number)[];
  /** Pydantic's error type, such as "missing", "string_too_short" or "extra_forbidden". */
  type: string;
};

/** What a decision call did. */
export type DecisionOutcome =
  /** The decision is on its way (watch `pending`). */
  | "sent"
  /** Request changes needs a comment; `commentMissing` is now true (focus the field). */
  | "comment_required"
  /** No change requests are left on this output: only approve (with or without edits) or reject. */
  | "no_attempts_left"
  /**
   * A decision is being sent or was just accepted, or a new version arrived and was not
   * acknowledged yet.
   */
  | "locked"
  /** The user may not decide on this run (`can_steer` is false). */
  | "not_allowed"
  /** No output waits for a decision. */
  | "no_output";

export type ApprovalCallbacks = {
  /** The API accepted the decision (202). `edited`: it was an approve with edits. */
  onDecided?: (decision: Decision, context: { edited: boolean }) => void;
  /**
   * 409: the reviewed output is no longer the one waiting (`approval.stale`, `.duplicate`,
   * `.rejected_by_workflow`). `conflict` is set and the run is refetched.
   */
  onConflict?: (error: ApiError) => void;
  /** Any other failure, including an invalid edit (then `invalidEdit` says where). */
  onError?: (error: ApiError) => void;
};

export type ApprovalDecision = {
  /** The output waiting for a decision, or null. */
  output: StageOutputOut | null;
  stage: string | null;
  /** An output waits and the user may decide on it. */
  canDecide: boolean;
  comment: string;
  setComment: (value: string) => void;
  /** Request changes was tried without a comment (cleared once there is one). */
  commentMissing: boolean;
  /** The last decision hit a 409: a newer output replaced the reviewed one, or someone decided. */
  conflict: boolean;
  /** The output changed since the reviewer started reading it; decisions wait for `acknowledge`. */
  updatedWhileOpen: boolean;
  /** The reviewer has read the new version: unlock the decisions (and clear `conflict`). */
  acknowledge: () => void;
  /** Decisions are refused: one is on its way or accepted (`sentDecision`), or `updatedWhileOpen`. */
  locked: boolean;
  /** A decision is being sent (until the run detail has been refetched). */
  pending: boolean;
  pendingDecision: Decision | null;
  /**
   * The decision the API accepted for the output on screen. The run detail can lag behind it
   * (the workflow records the decision a moment later), so the decisions stay locked until
   * another output, or none, waits for review.
   */
  sentDecision: Decision | null;
  /** The attempt the output under review belongs to; null until the run detail says. */
  attempt: ReviewAttempt | null;
  /** Change requests still possible (`attempts_left`): 0 leaves approve or reject; null if unknown. */
  changesLeft: number | null;
  /** Request changes may be sent: false once no change requests are left. */
  canRequestChanges: boolean;
  /** The last approve-with-edits was refused by the stage's schema. */
  invalidEdit: InvalidEdit | null;
  /** The last failure other than a conflict. */
  error: ApiError | null;
  approve: () => DecisionOutcome;
  requestChanges: () => DecisionOutcome;
  reject: () => DecisionOutcome;
  /** Approves a corrected output: the API stores it as a new version and approves that one. */
  approveWithEdits: (editedData: Record<string, unknown>) => DecisionOutcome;
};

/** A 422 `decision.invalid_edit`, with where the edit failed. */
class InvalidEditError extends ApiError {
  readonly edit: InvalidEdit;

  constructor(status: number | undefined, edit: InvalidEdit) {
    super("decision.invalid_edit", status);
    this.name = "InvalidEditError";
    this.edit = edit;
  }
}

type DecisionVariables = {
  /** The review the decision belongs to (see `reviewKeyOf`). */
  reviewKey: string;
  runId: string;
  outputId: string;
  sha256: string;
  decision: Decision;
  comment: string;
  editedData?: Record<string, unknown>;
};

/**
 * A fetch for one request that keeps a copy of an error response's JSON body: the client's
 * error interceptor (src/lib/api-client.ts) keeps only the message code, and an invalid edit's
 * `loc` and `type` come next to it.
 */
function keepingErrorBody(sink: { body?: unknown }): typeof fetch {
  const base = client.getConfig().fetch ?? globalThis.fetch;
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const response = await base(input, init);
    if (!response.ok) {
      sink.body = await response
        .clone()
        .json()
        .catch(() => undefined);
    }
    return response;
  };
}

function invalidEditError(error: ApiError, body: unknown): InvalidEditError {
  const fields =
    body && typeof body === "object" ? (body as { loc?: unknown; type?: unknown }) : {};
  const loc = Array.isArray(fields.loc)
    ? fields.loc.filter(
        (part): part is string | number => typeof part === "string" || typeof part === "number",
      )
    : [];
  return new InvalidEditError(error.status, {
    loc,
    type: typeof fields.type === "string" ? fields.type : "value_error",
  });
}

async function sendDecision(variables: DecisionVariables): Promise<void> {
  const errorBody: { body?: unknown } = {};
  try {
    await decideStage({
      path: { run_id: variables.runId },
      body: {
        stage_output_id: variables.outputId,
        sha256: variables.sha256,
        decision: variables.decision,
        comment: variables.comment,
        ...(variables.editedData ? { edited_data: variables.editedData } : {}),
      },
      fetch: keepingErrorBody(errorBody),
      throwOnError: true,
    });
  } catch (error) {
    if (error instanceof ApiError && error.code === "decision.invalid_edit") {
      throw invalidEditError(error, errorBody.body);
    }
    throw error;
  }
}

type Review = {
  key: string | null;
  /** sha256 of the version the reviewer has read. */
  seenHash: string;
  comment: string;
  commentMissing: boolean;
  conflict: boolean;
  invalidEdit: InvalidEdit | null;
  error: ApiError | null;
  /** The output a decision was accepted for, and the decision. */
  sent: { outputId: string; decision: Decision } | null;
};

function freshReview(key: string | null, output: StageOutputOut | null): Review {
  return {
    key,
    seenHash: output?.sha256 ?? "",
    comment: "",
    commentMissing: false,
    conflict: false,
    invalidEdit: null,
    error: null,
    sent: null,
  };
}

/** One review per run and waiting stage; a new version of the same stage keeps the review. */
function reviewKeyOf(run: ApprovalRun | null | undefined): string | null {
  return run?.awaiting ? `${run.id}/${run.awaiting_stage ?? ""}` : null;
}

function nonNegative(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

/**
 * The attempt of the output under review. With `attempts_left` it is counted within this
 * execution of the run ("2 of 3"; a retry starts a new execution while the stage's attempt
 * numbers keep counting); without, it is the stage's own count.
 */
function reviewAttemptOf(run: ApprovalRun, output: StageOutputOut): ReviewAttempt | null {
  const left = nonNegative(run.attempts_left);
  const max = nonNegative(run.max_attempts);
  if (left !== null && max !== null && left < max) {
    return { number: max - left, of: max };
  }
  const stageRun =
    run.stages.find((candidate) => candidate.outputs?.some((item) => item.id === output.id)) ??
    run.stages.filter((candidate) => candidate.stage === run.awaiting_stage).at(-1);
  return stageRun ? { number: stageRun.attempt, of: null } : null;
}

/**
 * Deciding on the output that waits for review (`POST /runs/{id}/approvals`): approve, request
 * changes, reject, or approve with edits. The decision carries the id and sha256 of the output
 * on screen, so the API answers 409 if it changed meanwhile.
 *
 * - Request changes needs a comment; approve and reject take an optional one. Comments are sent
 *   trimmed, and cleared after a decision is accepted.
 * - Request changes is refused once no change requests are left (`attempts_left` is 0; a 409
 *   `decision.no_attempts_left` refetches the run).
 * - When a new version of the waiting output arrives while the reviewer reads, decisions lock
 *   until `acknowledge()`. After a decision is accepted they stay locked (`sentDecision`) until
 *   the run detail shows another output, or none, waiting.
 * - A 409 sets `conflict` and refetches the run; a 422 `decision.invalid_edit` sets
 *   `invalidEdit` with the schema error's `loc`.
 * - The review starts over (comment, conflict, lock) when another stage's output waits or none
 *   does, as a freshly mounted panel would.
 *
 * The callbacks are for toasts and focus; the hook has no UI of its own.
 */
export function useApprovalDecision(
  run: ApprovalRun | null | undefined,
  callbacks: ApprovalCallbacks = {},
): ApprovalDecision {
  const queryClient = useQueryClient();
  const output = run?.awaiting ?? null;
  const stage = run?.awaiting ? (run.awaiting_stage ?? "") : null;
  const reviewKey = reviewKeyOf(run);

  const [stored, setReview] = useState<Review>(() => freshReview(reviewKey, output));
  let review = stored;
  if (stored.key !== reviewKey) {
    // Adjusts state while rendering (react.dev: "Storing information from previous renders").
    review = freshReview(reviewKey, output);
    setReview(review);
  }

  /** Changes the review `key` if it is still the current one (a late answer leaves others be). */
  const update = useCallback((key: string, change: Partial<Review>) => {
    setReview((current) => (current.key === key ? { ...current, ...change } : current));
  }, []);

  const mutation = useMutation({
    mutationFn: sendDecision,
    onSuccess: async (_data, variables) => {
      callbacks.onDecided?.(variables.decision, { edited: variables.editedData !== undefined });
      update(variables.reviewKey, {
        comment: "",
        conflict: false,
        sent: { outputId: variables.outputId, decision: variables.decision },
      });
      await invalidateRunQueries(queryClient, variables.runId);
    },
    onError: async (error, variables) => {
      const apiError = toApiError(error);
      if (APPROVAL_CONFLICT_CODES.has(apiError.code)) {
        update(variables.reviewKey, { conflict: true });
        callbacks.onConflict?.(apiError);
        await invalidateRunQueries(queryClient, variables.runId);
        return;
      }
      update(variables.reviewKey, {
        error: apiError,
        invalidEdit: apiError instanceof InvalidEditError ? apiError.edit : null,
        ...(apiError.code === "decision.comment_required" ? { commentMissing: true } : {}),
      });
      callbacks.onError?.(apiError);
      if (apiError.code === "decision.no_attempts_left") {
        // The run detail counted on an attempt that is gone: refetch, so that only approve
        // and reject are offered.
        await invalidateRunQueries(queryClient, variables.runId);
      }
    },
  });

  // A decision sent for another review (before this output arrived) does not lock this one.
  const pending = mutation.isPending && mutation.variables?.reviewKey === reviewKey;
  const updatedWhileOpen = output !== null && review.seenHash !== output.sha256;
  const sentDecision =
    output !== null && review.sent?.outputId === output.id ? review.sent.decision : null;
  const locked = pending || updatedWhileOpen || sentDecision !== null;
  const attempt = useMemo(
    () => (run && output ? reviewAttemptOf(run, output) : null),
    [run, output],
  );
  const changesLeft = output !== null ? nonNegative(run?.attempts_left) : null;
  const canRequestChanges = changesLeft !== 0;
  const { mutate } = mutation;

  const decide = useCallback(
    (decision: Decision, editedData?: Record<string, unknown>): DecisionOutcome => {
      if (!run || !output || reviewKey === null) {
        return "no_output";
      }
      if (!run.can_steer) {
        return "not_allowed";
      }
      if (locked) {
        return "locked";
      }
      if (decision === "request_changes" && !canRequestChanges) {
        return "no_attempts_left";
      }
      const comment = review.comment.trim();
      if (decision === "request_changes" && comment.length === 0) {
        update(reviewKey, { commentMissing: true });
        return "comment_required";
      }
      update(reviewKey, { commentMissing: false, error: null, invalidEdit: null });
      mutate({
        reviewKey,
        runId: run.id,
        outputId: output.id,
        sha256: output.sha256,
        decision,
        comment,
        editedData,
      });
      return "sent";
    },
    [run, output, reviewKey, locked, canRequestChanges, review.comment, update, mutate],
  );

  const setComment = useCallback(
    (value: string) => {
      if (reviewKey === null) {
        return;
      }
      setReview((current) =>
        current.key === reviewKey
          ? {
              ...current,
              comment: value,
              commentMissing: current.commentMissing && value.trim().length === 0,
            }
          : current,
      );
    },
    [reviewKey],
  );

  const acknowledge = useCallback(() => {
    if (reviewKey !== null && output) {
      update(reviewKey, { seenHash: output.sha256, conflict: false });
    }
  }, [reviewKey, output, update]);

  const actions = useMemo(
    () => ({
      approve: () => decide("approve"),
      requestChanges: () => decide("request_changes"),
      reject: () => decide("reject"),
      approveWithEdits: (editedData: Record<string, unknown>) => decide("approve", editedData),
    }),
    [decide],
  );

  return {
    output,
    stage,
    canDecide: run?.can_steer === true && output !== null,
    comment: review.comment,
    setComment,
    commentMissing: review.commentMissing,
    conflict: review.conflict,
    updatedWhileOpen,
    acknowledge,
    locked,
    pending,
    pendingDecision: pending ? (mutation.variables?.decision ?? null) : null,
    sentDecision,
    attempt,
    changesLeft,
    canRequestChanges,
    invalidEdit: review.invalidEdit,
    error: review.error,
    ...actions,
  };
}

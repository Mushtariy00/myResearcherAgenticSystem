/**
 * API errors arrive as `{"detail": "<message.code>"}` (FastAPI). Every failure is turned into an
 * ApiError with a code that has a translation under `errors.*` in messages/{en,ko}.json.
 */

/** Codes the UI translates. Unknown codes fall back to `server.error` or `unknown`. */
export const KNOWN_ERROR_CODES = [
  "auth.required",
  "auth.unavailable",
  "csrf.origin_mismatch",
  "permission.denied",
  "project.not_found",
  "run.not_found",
  "user.not_found",
  "stage_output.not_found",
  "approval.stale",
  "approval.duplicate",
  "approval.rejected_by_workflow",
  "run.already_finished",
  "run.not_retryable",
  "stage.not_reached",
  "stage.not_found",
  "decision.invalid",
  "decision.edit_requires_approve",
  "decision.invalid_edit",
  "decision.edit_too_large",
  "decision.no_attempts_left",
  "decision.comment_required",
  "papers.invalid_year_range",
  "member.last_owner",
  "member.not_found",
  "member.exists",
  "paper.not_found",
  "artifact.not_found",
  "orchestrator.unavailable",
  "db.unavailable",
  // Stored on runs and stages by the worker (apps/worker).
  "stage.error",
  "stage.too_many_attempts",
  "stage.invalid_output",
  "approval.expired",
  "lab_balance.exhausted",
  "free_models.disabled",
  "free_quota.exhausted",
  "gateway.error",
  "db.error",
  "validation.failed",
  "network.error",
  "server.error",
  "unknown",
] as const;

export type ErrorCode = (typeof KNOWN_ERROR_CODES)[number];

const KNOWN = new Set<string>(KNOWN_ERROR_CODES);
const CODE_PATTERN = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/;

/** The approval conflicts that mean "the output you reviewed is no longer the one waiting". */
export const APPROVAL_CONFLICT_CODES = new Set<string>([
  "approval.stale",
  "approval.duplicate",
  "approval.rejected_by_workflow",
]);

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | undefined;

  constructor(code: string, status?: number) {
    super(code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** Normalises whatever the fetch client threw (parsed JSON body, text, TypeError) into ApiError. */
export function toApiError(error: unknown, status?: number): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (status === undefined) {
    return new ApiError("network.error");
  }
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string" && CODE_PATTERN.test(detail)) {
      return new ApiError(detail, status);
    }
    if (Array.isArray(detail)) {
      return new ApiError("validation.failed", status); // FastAPI request validation (422)
    }
  }
  return new ApiError(status >= 500 ? "server.error" : "unknown", status);
}

/** The `errors.*` message key to show for an error. */
export function errorMessageKey(error: unknown): ErrorCode {
  const apiError = toApiError(error, error instanceof ApiError ? error.status : undefined);
  if (KNOWN.has(apiError.code)) {
    return apiError.code as ErrorCode;
  }
  return apiError.status !== undefined && apiError.status >= 500 ? "server.error" : "unknown";
}

/** Run errors stored on the run (e.g. `orchestrator.unavailable`) use the same codes. */
export function isKnownErrorCode(value: string | null | undefined): value is ErrorCode {
  return typeof value === "string" && KNOWN.has(value);
}

/**
 * The message key for an error stored on a run or stage (null when there is none). The worker
 * reports schema failures per stage (`method.invalid_output`), which share one message, and
 * anything else this UI does not know, such as a newer code or an exception's raw text, reads as
 * the generic `stage.error`: raw text is untranslated and may name internal hosts.
 */
export function runErrorKey(value: string | null | undefined): ErrorCode | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }
  if (isKnownErrorCode(value)) {
    return value;
  }
  return /^[a-z_]+\.invalid_output$/.test(value) ? "stage.invalid_output" : "stage.error";
}

/** Why a stage output is flagged `degraded` (translated under `degradedReasons.*`). */
export const KNOWN_DEGRADED_REASONS = [
  "stage.placeholder",
  "literature.search_pending",
  // Demo outputs: the stage is not built yet, its output is generated (agentic_core.demo).
  "literature.demo_search",
  "stage.demo",
  // Real literature searches that came back incomplete (docs/design/literature.md).
  "literature.partial_search",
  "literature.no_full_text",
] as const;

/** Degraded reasons that mean "generated demo data", shown with a Demo badge. */
export const DEMO_DEGRADED_REASONS = new Set<string>(["literature.demo_search", "stage.demo"]);

export type DegradedReason = (typeof KNOWN_DEGRADED_REASONS)[number];

export function isKnownDegradedReason(value: string | null | undefined): value is DegradedReason {
  return typeof value === "string" && (KNOWN_DEGRADED_REASONS as readonly string[]).includes(value);
}

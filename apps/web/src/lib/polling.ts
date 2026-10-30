import { focusManager } from "@tanstack/react-query";
import { toApiError } from "./api-error";

/**
 * Polling that runs only while the page is visible, shared by every live hook (GPU queue,
 * notifications, system health) in both interfaces.
 *
 * Spread `pollWhileVisible(ms)` into a query's options:
 * - while the page is hidden the timer is cleared (and TanStack Query skips any tick that is
 *   still scheduled), so a background tab sends no requests;
 * - coming back refetches at once (`refetchOnWindowFocus: "always"`), which also restarts the
 *   timer;
 * - after a server or network failure it polls more slowly until a fetch succeeds again; after a
 *   client error (401, 403, 404...) it stops, since asking again will not change the answer.
 *
 * "Visible" is TanStack Query's focus state: the document's `visibilityState`, unless something
 * set it explicitly with `focusManager.setFocused`.
 */

/** Polling cadences of the shared hooks, in milliseconds. */
export const POLL_INTERVALS = {
  gpuQueue: 5_000,
  systemHealth: 15_000,
  notifications: 20_000,
} as const;

/** The slowest cadence after failures, in milliseconds. */
const MAX_ERROR_INTERVAL_MS = 120_000;

/** Client errors a later attempt may not repeat: timeouts and rate limits. */
const TRANSIENT_CLIENT_STATUSES = new Set([408, 425, 429]);

export type PollOptions = {
  /** Interval after a failure that may go away (5xx, timeout, rate limit, network). Default: 3x the interval, at least 30 s. */
  errorIntervalMs?: number;
};

/** The part of a TanStack `Query` the interval depends on. */
export type PolledQuery = {
  state: { status: "pending" | "error" | "success"; error: unknown };
};

/** Whether the page is visible, as TanStack Query sees it. */
export function isPageVisible(): boolean {
  return focusManager.isFocused();
}

/**
 * The refetch interval a polled query should use right now: `false` (no timer) while the page is
 * hidden or after a client error, the slower error interval after other failures, otherwise
 * `intervalMs`.
 */
export function pollInterval(
  intervalMs: number,
  query: PolledQuery,
  options: PollOptions = {},
  visible: boolean = isPageVisible(),
): number | false {
  if (!visible) {
    return false;
  }
  if (query.state.status !== "error") {
    return intervalMs;
  }
  const status = toApiError(query.state.error).status;
  if (status !== undefined && status < 500 && !TRANSIENT_CLIENT_STATUSES.has(status)) {
    return false;
  }
  return (
    options.errorIntervalMs ?? Math.min(Math.max(intervalMs * 3, 30_000), MAX_ERROR_INTERVAL_MS)
  );
}

/** TanStack Query options for a query that polls every `intervalMs` while the page is visible. */
export function pollWhileVisible(intervalMs: number, options: PollOptions = {}) {
  return {
    refetchInterval: (query: PolledQuery) => pollInterval(intervalMs, query, options),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
  } as const;
}

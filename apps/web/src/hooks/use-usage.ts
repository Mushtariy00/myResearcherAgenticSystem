"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { GetUsageError, UsageOut } from "@/client";
import { getUsageOptions } from "@/client/@tanstack/react-query.gen";

export type UsageScope = UsageOut["scope"];

/** The API accepts 7..90 days (UTC days, today included). */
export const USAGE_DAYS = { min: 7, max: 90, default: 30 } as const;

function clampDays(days: number): number {
  return Number.isFinite(days)
    ? Math.min(USAGE_DAYS.max, Math.max(USAGE_DAYS.min, Math.round(days)))
    : USAGE_DAYS.default;
}

/**
 * LLM spend and calls from the journal (real figures, zeros on quiet days): the caller's own
 * ("me") or the whole lab's ("lab", lab admins only: 403 otherwise). Totals, every day of the
 * window, the most expensive models and runs, per-user rows for the lab, and the caller's budget
 * this month. Switching the window keeps the previous figures on screen until the new ones
 * arrive (`isPlaceholderData`), but switching scope never shows the other scope's figures.
 */
export function useUsage(
  scope: UsageScope = "me",
  days: number = USAGE_DAYS.default,
  options: { enabled?: boolean } = {},
): UseQueryResult<UsageOut, GetUsageError> {
  return useQuery({
    ...getUsageOptions({ query: { scope, days: clampDays(days) } }),
    enabled: options.enabled ?? true,
    placeholderData: (previous) => (previous?.scope === scope ? previous : undefined),
    staleTime: 60_000,
  });
}

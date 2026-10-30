"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { LabBalanceOut } from "@/client";
import { getLabBalanceOptions } from "@/client/@tanstack/react-query.gen";

/**
 * Admin: the lab's prepaid OpenRouter balance and its alert floor (`below_floor`), this month's
 * paid spend of every user, and the free-model calls used today against the daily limit.
 * Lab admins only (403 otherwise).
 */
export function useLabBalance(): UseQueryResult<LabBalanceOut, Error> {
  return useQuery({ ...getLabBalanceOptions(), staleTime: 60_000 });
}

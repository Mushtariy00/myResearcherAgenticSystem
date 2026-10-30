"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { ModelRoutingOut } from "@/client";
import { getModelRoutingOptions } from "@/client/@tanstack/react-query.gen";

/**
 * Admin: per agent role, the paid and free model chains the gateway tries (in order, with
 * catalog prices and context lengths), and the real state of the paid-models kill switch.
 * Lab admins only (403 otherwise).
 */
export function useModelRouting(): UseQueryResult<ModelRoutingOut, Error> {
  return useQuery({ ...getModelRoutingOptions(), staleTime: 30_000 });
}

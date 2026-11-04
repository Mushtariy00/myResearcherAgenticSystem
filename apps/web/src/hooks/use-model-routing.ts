"use client";

import { type UseQueryResult, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ModelCatalogOut, ModelRoutingOut } from "@/client";
import {
  getModelCatalogOptions,
  getModelRoutingOptions,
  getModelRoutingQueryKey,
  setRoleModelsMutation,
} from "@/client/@tanstack/react-query.gen";

/**
 * Admin: per agent role, the paid and free model chains the gateway tries (in order, with
 * catalog prices and context lengths), and the real state of the paid-models kill switch.
 * Lab admins only (403 otherwise).
 */
export function useModelRouting(): UseQueryResult<ModelRoutingOut, Error> {
  return useQuery({ ...getModelRoutingOptions(), staleTime: 30_000 });
}

/** Admin: the text models OpenRouter offers, as the gateway last read them, to choose from. */
export function useModelCatalog(): UseQueryResult<ModelCatalogOut, Error> {
  return useQuery({ ...getModelCatalogOptions(), staleTime: 5 * 60_000 });
}

/**
 * Admin: give an agent role its own model chains, or put it back on the lab's (`null`). The
 * answer is the whole routing view, so the page shows what was saved without another request.
 */
export function useSetRoleModels() {
  const queryClient = useQueryClient();
  return useMutation({
    ...setRoleModelsMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getModelRoutingQueryKey(), data);
    },
  });
}

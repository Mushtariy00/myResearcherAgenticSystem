"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { DatasetList } from "@/client";
import { listDatasetsOptions } from "@/client/@tanstack/react-query.gen";

/**
 * Datasets experiments can mount read-only, with their splits and data contracts. An item's
 * `id` is the value of the new-run option `config.dataset`. `size_bytes` and `checksum_sha256`
 * are null until the GPU executor has measured the dataset: show them as unknown, never as 0.
 * The registry rarely changes, so it is cached for 5 minutes.
 */
export function useDatasets(): UseQueryResult<DatasetList, Error> {
  return useQuery({ ...listDatasetsOptions(), staleTime: 5 * 60_000 });
}

"use client";

import { keepPreviousData, type UseQueryResult, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import type { LibraryPaperOut, ListPapersData, ListPapersError, PaperPage } from "@/client";
import { listPapersOptions } from "@/client/@tanstack/react-query.gen";

type PapersQuery = NonNullable<ListPapersData["query"]>;
export type ScreeningDecision = NonNullable<PapersQuery["decision"]>;
export type PaperSource = NonNullable<PapersQuery["source"]>;

/** The API's limits for GET /api/v1/papers, and the hook's defaults. */
export const PAPER_SEARCH = {
  pageSize: 20,
  maxPageSize: 200,
  debounceMs: 300,
  maxQueryLength: 200,
  minYear: 1900,
  maxYear: 2100,
} as const;

/**
 * `value`, once it has stopped changing for `delayMs`. The first value is returned at once, so
 * the first request is not delayed.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export type PaperSearchParams = {
  /** Search text (title, abstract, an author or the venue); debounced, trimmed, max 200 chars. */
  q?: string;
  projectId?: string | null;
  yearFrom?: number | null;
  yearTo?: number | null;
  decision?: ScreeningDecision | null;
  source?: PaperSource | null;
  /** Papers per page, 1..200 (default 20). */
  pageSize?: number;
  /** Wait this long after the last keystroke before searching (default 300 ms). */
  debounceMs?: number;
};

export type PaperSearch = {
  /** The page query (TanStack). While new results load, it keeps the previous ones. */
  query: UseQueryResult<PaperPage, ListPapersError>;
  /** The papers of the current page, best relevance first; [] until the first page arrives. */
  items: LibraryPaperOut[];
  /** Papers matching the filters, over every page. */
  total: number;
  /** Some of the results are generated demo content. */
  demo: boolean;
  /** The search text the results are for (q after the debounce). */
  searchedQ: string;
  /** The results do not match the inputs yet: typing has not settled, or the next page is loading. */
  isSearching: boolean;
  /** A year filter is outside 1900..2100 or after the other: nothing is fetched until it is fixed. */
  yearRangeInvalid: boolean;
  /** 0-based; back to 0 whenever the search text or a filter changes. */
  pageIndex: number;
  pageSize: number;
  /** At least 1. */
  pageCount: number;
  hasPreviousPage: boolean;
  hasNextPage: boolean;
  setPageIndex: (pageIndex: number) => void;
  nextPage: () => void;
  previousPage: () => void;
};

function isYear(value: number | null | undefined): boolean {
  return (
    value === null ||
    value === undefined ||
    (Number.isInteger(value) && value >= PAPER_SEARCH.minYear && value <= PAPER_SEARCH.maxYear)
  );
}

function clampPageSize(pageSize: number | undefined): number {
  const size = Math.floor(pageSize ?? PAPER_SEARCH.pageSize);
  return Number.isFinite(size)
    ? Math.min(PAPER_SEARCH.maxPageSize, Math.max(1, size))
    : PAPER_SEARCH.pageSize;
}

/**
 * The paper library (GET /api/v1/papers): papers of the caller's projects, every project for lab
 * admins. The search text is debounced; filters apply at once. Paging is kept here so both
 * interfaces page the same way: it resets when the search or a filter changes.
 */
export function usePaperSearch(params: PaperSearchParams = {}): PaperSearch {
  const pageSize = clampPageSize(params.pageSize);
  const typed = (params.q ?? "").trim().slice(0, PAPER_SEARCH.maxQueryLength);
  const searchedQ = useDebouncedValue(typed, params.debounceMs ?? PAPER_SEARCH.debounceMs);
  const { projectId, yearFrom, yearTo, decision, source } = params;
  const yearRangeInvalid =
    !isYear(yearFrom) ||
    !isYear(yearTo) ||
    (typeof yearFrom === "number" && typeof yearTo === "number" && yearFrom > yearTo);

  // Paging belongs to one set of filters: a page chosen for other filters reads as page 0.
  const filtersKey = JSON.stringify([
    searchedQ,
    projectId ?? null,
    yearFrom ?? null,
    yearTo ?? null,
    decision ?? null,
    source ?? null,
    pageSize,
  ]);
  const [paging, setPaging] = useState({ filtersKey, pageIndex: 0 });
  const pageIndex = paging.filtersKey === filtersKey ? paging.pageIndex : 0;

  const filters: PapersQuery = { limit: pageSize, offset: pageIndex * pageSize };
  if (searchedQ) {
    filters.q = searchedQ;
  }
  if (projectId) {
    filters.project_id = projectId;
  }
  if (typeof yearFrom === "number") {
    filters.year_from = yearFrom;
  }
  if (typeof yearTo === "number") {
    filters.year_to = yearTo;
  }
  if (decision) {
    filters.decision = decision;
  }
  if (source) {
    filters.source = source;
  }

  const query = useQuery({
    ...listPapersOptions({ query: filters }),
    enabled: !yearRangeInvalid,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const setPageIndex = useCallback(
    (next: number) => setPaging({ filtersKey, pageIndex: Math.max(0, Math.floor(next) || 0) }),
    [filtersKey],
  );

  return {
    query,
    items: query.data?.items ?? [],
    total,
    demo: query.data?.demo ?? false,
    searchedQ,
    isSearching: typed !== searchedQ || (query.isFetching && query.isPlaceholderData),
    yearRangeInvalid,
    pageIndex,
    pageSize,
    pageCount,
    hasPreviousPage: pageIndex > 0,
    hasNextPage: pageIndex + 1 < pageCount,
    setPageIndex,
    nextPage: () => setPageIndex(Math.min(pageIndex + 1, pageCount - 1)),
    previousPage: () => setPageIndex(pageIndex - 1),
  };
}

import type { LibraryPaperOut, PaperRef } from "@/client";
import type { PaperSearchParams, PaperSource, ScreeningDecision } from "@/hooks/use-paper-search";

/** Screening decisions in the order the API lists them, most favourable first. */
export const SCREENING_DECISIONS = [
  "include",
  "maybe",
  "exclude",
] as const satisfies readonly ScreeningDecision[];

/** Where library papers can come from, in display order. */
export const PAPER_SOURCES = [
  "arxiv",
  "semantic_scholar",
  "openalex",
  "crossref",
  "core",
  "demo",
] as const satisfies readonly PaperSource[];

/** The library's search box and filters as their inputs hold them (years as typed). */
export type PaperFilters = {
  q: string;
  yearFrom: string;
  yearTo: string;
  decision: ScreeningDecision | null;
  source: PaperSource | null;
};

export const NO_PAPER_FILTERS: Readonly<PaperFilters> = {
  q: "",
  yearFrom: "",
  yearTo: "",
  decision: null,
  source: null,
};

export function hasPaperFilters(filters: PaperFilters): boolean {
  return (
    filters.q.trim() !== "" ||
    filters.yearFrom.trim() !== "" ||
    filters.yearTo.trim() !== "" ||
    filters.decision !== null ||
    filters.source !== null
  );
}

/** A typed year: null when empty, NaN when it is not a whole number (the search reports it). */
export function yearOf(text: string): number | null {
  const value = text.trim();
  if (value === "") {
    return null;
  }
  return /^\d+$/.test(value) ? Number(value) : Number.NaN;
}

export function isScreeningDecision(value: unknown): value is ScreeningDecision {
  return typeof value === "string" && (SCREENING_DECISIONS as readonly string[]).includes(value);
}

export function isPaperSource(value: unknown): value is PaperSource {
  return typeof value === "string" && (PAPER_SOURCES as readonly string[]).includes(value);
}

/** The `usePaperSearch` parameters for these filters, within one project or the whole library. */
export function paperSearchParams(
  filters: PaperFilters,
  projectId?: string | null,
): PaperSearchParams {
  return {
    q: filters.q,
    projectId: projectId ?? null,
    yearFrom: yearOf(filters.yearFrom),
    yearTo: yearOf(filters.yearTo),
    decision: filters.decision,
    source: filters.source,
  };
}

/**
 * A library entry as the shared PapersTable shows it: its best relevance and the decision that
 * matched the filter, else its most favourable one (a paper screened by several runs has one
 * per run). The library keeps no single reason, so none is shown.
 */
export function toPaperRow(item: LibraryPaperOut, decision?: ScreeningDecision | null): PaperRef {
  return {
    ...item.paper,
    relevance: item.best_relevance ?? 0,
    decision: decision ?? item.decisions[0] ?? "maybe",
    decision_reason: "",
  };
}

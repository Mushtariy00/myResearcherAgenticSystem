import type { LibraryPaperOut, PaperRef } from "@/client";
import { bestDecision } from "./paper-meta";

/**
 * A library paper in the shape of a literature output's paper (`PaperRef`), for the shared
 * PapersTable: its best relevance over the runs that found it, and its most favourable
 * screening decision.
 */
export function toPaperRef(item: LibraryPaperOut): PaperRef {
  return {
    ...item.paper,
    relevance: item.best_relevance ?? 0,
    decision: bestDecision(item.decisions) ?? "maybe",
    decision_reason: "",
  };
}

/** A year typed into a filter field: a whole number, or null while the field is empty. */
export function yearFilter(value: string): number | null {
  const text = value.trim();
  if (text === "") {
    return null;
  }
  const year = Number(text);
  return Number.isInteger(year) ? year : Number.NaN;
}

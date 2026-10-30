import type { PaperRef } from "@/client";

/**
 * What the shared components need to name a paper. Both the literature output's `PaperRef`
 * and the library's `PaperOut` fit.
 */
export type PaperSummary = Pick<PaperRef, "paper_id" | "title" | "authors" | "year"> & {
  venue?: string | null;
  pdf_available?: boolean;
};

export function indexPapers<T extends PaperSummary>(
  papers: readonly T[] | undefined,
): ReadonlyMap<string, T> {
  return new Map((papers ?? []).map((paper) => [paper.paper_id, paper]));
}

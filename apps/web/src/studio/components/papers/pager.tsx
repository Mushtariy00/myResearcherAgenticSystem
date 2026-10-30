"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { PaperSearch } from "@/hooks/use-paper-search";
import { cn } from "@/lib/utils";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";

/** Previous / next page of a paper search, with "Page 2 of 5". Hidden for a single page. */
export function Pager({ search, label }: { search: PaperSearch; label: string }) {
  const t = useTranslations("studioWork.papers.pager");
  if (search.pageCount <= 1) {
    return null;
  }
  return (
    <nav aria-label={label} className="flex items-center justify-between gap-3">
      <button
        type="button"
        onClick={search.previousPage}
        disabled={!search.hasPreviousPage}
        className={cn(OUTLINE_BUTTON, "h-9 px-3 disabled:pointer-events-none disabled:opacity-50")}
      >
        <ChevronLeftIcon aria-hidden />
        {t("previous")}
      </button>
      <p className="text-xs text-muted-foreground tabular-nums">
        {t("page", { page: search.pageIndex + 1, total: search.pageCount })}
      </p>
      <button
        type="button"
        onClick={search.nextPage}
        disabled={!search.hasNextPage}
        className={cn(OUTLINE_BUTTON, "h-9 px-3 disabled:pointer-events-none disabled:opacity-50")}
      >
        {t("next")}
        <ChevronRightIcon aria-hidden />
      </button>
    </nav>
  );
}

"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { PapersTable } from "@/components/shared/papers-table";
import { Button } from "@/components/ui/button";
import { type PaperSearch, usePaperSearch } from "@/hooks/use-paper-search";
import { cn } from "@/lib/utils";
import {
  hasPaperFilters,
  NO_PAPER_FILTERS,
  type PaperFilters,
  paperSearchParams,
  toPaperRow,
} from "./library";
import { PaperFilterBar } from "./paper-filters";
import { PaperSheet } from "./paper-sheet";

function PaperPagination({ search }: { search: PaperSearch }) {
  const t = useTranslations("papers.pagination");
  if (search.pageCount <= 1) {
    return null;
  }
  return (
    <nav aria-label={t("label")} className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm text-muted-foreground tabular-nums">
        {t("page", { page: search.pageIndex + 1, count: search.pageCount })}
      </p>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={search.previousPage}
          disabled={!search.hasPreviousPage}
        >
          <ChevronLeftIcon aria-hidden />
          {t("previous")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={search.nextPage}
          disabled={!search.hasNextPage}
        >
          {t("next")}
          <ChevronRightIcon aria-hidden />
        </Button>
      </div>
    </nav>
  );
}

export type PaperBrowserProps = {
  /** Only this project's papers; the whole library (every project of the caller) without it. */
  projectId?: string;
};

/**
 * The paper library: full-text search, year, decision and source filters, a page of papers in
 * the shared PapersTable, paging, and a side sheet for the paper a row opens. Used by the
 * library page and by a project's Papers tab.
 */
export function PaperBrowser({ projectId }: PaperBrowserProps) {
  const t = useTranslations("papers.results");
  const format = useFormatter();
  const [filters, setFilters] = useState<PaperFilters>(NO_PAPER_FILTERS);
  const [openId, setOpenId] = useState<string | null>(null);
  const search = usePaperSearch(paperSearchParams(filters, projectId));
  const { query } = search;
  const rows = useMemo(
    () => search.items.map((item) => toPaperRow(item, filters.decision)),
    [search.items, filters.decision],
  );
  // A disabled search (an invalid year range before anything loaded) is not loading.
  const loading = query.isPending && query.fetchStatus !== "idle";
  const filtered = hasPaperFilters(filters);
  const first = search.pageIndex * search.pageSize + 1;

  return (
    <div className="grid gap-4">
      <PaperFilterBar
        value={filters}
        onChange={setFilters}
        yearRangeInvalid={search.yearRangeInvalid}
      />
      {query.isError ? (
        <QueryError error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
          <div
            className="flex min-h-5 flex-wrap items-center gap-2 text-sm text-muted-foreground"
            aria-live="polite"
          >
            {query.isSuccess && (
              <span className="tabular-nums">
                {search.total === 0
                  ? t("none")
                  : t("range", {
                      from: format.number(first),
                      to: format.number(first + search.items.length - 1),
                      total: search.total,
                    })}
              </span>
            )}
            {search.isSearching && <span>{t("searching")}</span>}
            <DemoBadge demo={search.demo} />
          </div>
          <div
            className={cn(
              "transition-opacity",
              (search.isSearching || search.yearRangeInvalid) && "opacity-60",
            )}
          >
            <PapersTable
              papers={rows}
              loading={loading}
              selectedId={openId}
              onSelect={(paper) => setOpenId(paper.paper_id)}
              caption={t("caption")}
              emptyMessage={
                filtered ? t("noMatches") : projectId ? t("emptyProject") : t("emptyLibrary")
              }
            />
          </div>
          <PaperPagination search={search} />
        </>
      )}
      <PaperSheet paperId={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}

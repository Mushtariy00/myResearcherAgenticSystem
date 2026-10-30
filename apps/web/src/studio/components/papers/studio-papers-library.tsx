"use client";

import { Toggle } from "@base-ui/react/toggle";
import { ToggleGroup } from "@base-ui/react/toggle-group";
import { useQuery } from "@tanstack/react-query";
import { LayoutGridIcon, LibraryIcon, SearchXIcon, TableIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useState } from "react";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { DemoBadge } from "@/components/shared/demo-badge";
import { PapersTable } from "@/components/shared/papers-table";
import {
  PAPER_SEARCH,
  type PaperSource,
  type ScreeningDecision,
  usePaperSearch,
} from "@/hooks/use-paper-search";
import { cn } from "@/lib/utils";
import {
  STUDIO_FIELD,
  StudioSearchInput,
  StudioSelect,
} from "@/studio/components/dashboard/studio-fields";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { glassClassName } from "@/studio/lib/glass";
import { FADE, SPRING } from "@/studio/lib/motion";
import { studioPaperPath } from "@/studio/lib/nav";
import { GHOST_BUTTON } from "@/studio/lib/ui";
import { toPaperRef, yearFilter } from "./library";
import { Pager } from "./pager";
import { PaperCard } from "./paper-card";

const PAGE_SIZE = 24;
const DECISIONS = ["include", "maybe", "exclude"] as const satisfies readonly ScreeningDecision[];
const SOURCES = [
  "arxiv",
  "semantic_scholar",
  "openalex",
  "crossref",
  "core",
  "demo",
] as const satisfies readonly PaperSource[];
const VIEWS = ["grid", "table"] as const;
type View = (typeof VIEWS)[number];

function oneOf<T extends string>(values: readonly T[], value: string): T | null {
  return (values as readonly string[]).includes(value) ? (value as T) : null;
}

/** Keeps the search text in the address (`?q=`), so a search can be reloaded and shared. */
function rememberQuery(q: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  if (q) {
    url.searchParams.set("q", q);
  } else {
    url.searchParams.delete("q");
  }
  const next = `${url.pathname}${url.search}${url.hash}`;
  if (next !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    window.history.replaceState(window.history.state, "", next);
  }
}

/**
 * The Studio paper library (usePaperSearch): every paper the caller's runs found. Search as you
 * type (debounced by the hook; the address keeps the text), filters for project, years,
 * screening decision and source, and results as a grid of cards or the shared sortable table,
 * switched with a sliding toggle. Generated papers carry the Demo badge.
 */
export function StudioPapersLibrary({ initialQuery = "" }: { initialQuery?: string }) {
  const t = useTranslations("studioWork.papers");
  const tAll = useTranslations();
  const router = useRouter();
  const ids = useId();
  const [q, setQ] = useState(initialQuery.slice(0, PAPER_SEARCH.maxQueryLength));
  const [projectId, setProjectId] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [decision, setDecision] = useState<ScreeningDecision | "">("");
  const [source, setSource] = useState<PaperSource | "">("");
  const [view, setView] = useState<View>("grid");
  const projects = useQuery(listProjectsOptions());
  const search = usePaperSearch({
    q,
    projectId: projectId || null,
    yearFrom: yearFilter(yearFrom),
    yearTo: yearFilter(yearTo),
    decision: decision || null,
    source: source || null,
    pageSize: PAGE_SIZE,
  });
  const papers = useMemo(() => search.items.map(toPaperRef), [search.items]);
  const filtered = Boolean(
    search.searchedQ || projectId || yearFrom || yearTo || decision || source,
  );
  const loading = search.query.isPending && !search.yearRangeInvalid;

  useEffect(() => {
    rememberQuery(search.searchedQ);
  }, [search.searchedQ]);

  function clearFilters() {
    setQ("");
    setProjectId("");
    setYearFrom("");
    setYearTo("");
    setDecision("");
    setSource("");
  }

  return (
    <div className="grid min-w-0 gap-6 lg:gap-8">
      <header className="studio-rise grid gap-2">
        <h1 className="studio-display flex flex-wrap items-center gap-3 text-3xl text-foreground sm:text-4xl">
          {t("title")}
          <DemoBadge demo={search.demo} />
        </h1>
        <p className="max-w-2xl text-base text-pretty text-muted-foreground">{t("description")}</p>
      </header>

      <search className="grid gap-4" aria-label={t("searchLabel")}>
        <div className="grid gap-1.5">
          <label htmlFor={`${ids}-q`} className="text-sm font-medium text-foreground">
            {t("search")}
          </label>
          <StudioSearchInput
            id={`${ids}-q`}
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={t("searchPlaceholder")}
            maxLength={PAPER_SEARCH.maxQueryLength}
            autoComplete="off"
            className="[&_input]:h-12 [&_input]:text-base"
          />
        </div>
        <div className="grid gap-3 min-[420px]:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_repeat(2,minmax(0,0.7fr))_repeat(2,minmax(0,1fr))]">
          <div className="grid min-w-0 gap-1.5 min-[420px]:col-span-2 lg:col-span-1">
            <label htmlFor={`${ids}-project`} className="text-xs font-medium text-muted-foreground">
              {t("filters.project")}
            </label>
            <StudioSelect
              id={`${ids}-project`}
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            >
              <option value="">{t("filters.anyProject")}</option>
              {projects.data?.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </StudioSelect>
          </div>
          <div className="grid min-w-0 gap-1.5">
            <label htmlFor={`${ids}-from`} className="text-xs font-medium text-muted-foreground">
              {t("filters.yearFrom")}
            </label>
            <input
              id={`${ids}-from`}
              type="number"
              inputMode="numeric"
              min={PAPER_SEARCH.minYear}
              max={PAPER_SEARCH.maxYear}
              value={yearFrom}
              onChange={(event) => setYearFrom(event.target.value)}
              aria-invalid={search.yearRangeInvalid || undefined}
              aria-describedby={search.yearRangeInvalid ? `${ids}-years` : undefined}
              className={cn(STUDIO_FIELD, "font-mono tabular-nums")}
            />
          </div>
          <div className="grid min-w-0 gap-1.5">
            <label htmlFor={`${ids}-to`} className="text-xs font-medium text-muted-foreground">
              {t("filters.yearTo")}
            </label>
            <input
              id={`${ids}-to`}
              type="number"
              inputMode="numeric"
              min={PAPER_SEARCH.minYear}
              max={PAPER_SEARCH.maxYear}
              value={yearTo}
              onChange={(event) => setYearTo(event.target.value)}
              aria-invalid={search.yearRangeInvalid || undefined}
              aria-describedby={search.yearRangeInvalid ? `${ids}-years` : undefined}
              className={cn(STUDIO_FIELD, "font-mono tabular-nums")}
            />
          </div>
          <div className="grid min-w-0 gap-1.5">
            <label
              htmlFor={`${ids}-decision`}
              className="text-xs font-medium text-muted-foreground"
            >
              {t("filters.decision")}
            </label>
            <StudioSelect
              id={`${ids}-decision`}
              value={decision}
              onChange={(event) => setDecision(oneOf(DECISIONS, event.target.value) ?? "")}
            >
              <option value="">{t("filters.anyDecision")}</option>
              {DECISIONS.map((value) => (
                <option key={value} value={value}>
                  {tAll(`shared.papers.decisions.${value}`)}
                </option>
              ))}
            </StudioSelect>
          </div>
          <div className="grid min-w-0 gap-1.5">
            <label htmlFor={`${ids}-source`} className="text-xs font-medium text-muted-foreground">
              {t("filters.source")}
            </label>
            <StudioSelect
              id={`${ids}-source`}
              value={source}
              onChange={(event) => setSource(oneOf(SOURCES, event.target.value) ?? "")}
            >
              <option value="">{t("filters.anySource")}</option>
              {SOURCES.map((value) => (
                <option key={value} value={value}>
                  {tAll(`shared.papers.sources.${value}`)}
                </option>
              ))}
            </StudioSelect>
          </div>
        </div>
        {search.yearRangeInvalid && (
          <p
            id={`${ids}-years`}
            data-tone="danger"
            className="text-xs font-medium text-(--tone-fg)"
          >
            {t("yearsInvalid", { min: PAPER_SEARCH.minYear, max: PAPER_SEARCH.maxYear })}
          </p>
        )}
      </search>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p
          role="status"
          className="flex min-h-6 items-center gap-2 text-sm text-muted-foreground tabular-nums"
        >
          {search.isSearching ? (
            <>
              <PulseDot tone="info" live size="sm" />
              {t("searching")}
            </>
          ) : search.query.isSuccess ? (
            search.searchedQ ? (
              t("resultsFor", { count: search.total, q: search.searchedQ })
            ) : (
              t("results", { count: search.total })
            )
          ) : null}
        </p>
        <div className="flex items-center gap-2">
          {filtered && (
            <button type="button" onClick={clearFilters} className={cn(GHOST_BUTTON, "h-9")}>
              {t("clearFilters")}
            </button>
          )}
          <ToggleGroup
            value={[view]}
            onValueChange={(next) => {
              const chosen = oneOf(VIEWS, next[0] ?? "");
              if (chosen) {
                setView(chosen);
              }
            }}
            aria-label={t("view.label")}
            className="studio-glass relative inline-flex items-center gap-1 rounded-xl p-1"
          >
            {VIEWS.map((value) => {
              const Icon = value === "grid" ? LayoutGridIcon : TableIcon;
              const active = view === value;
              return (
                <Toggle
                  key={value}
                  value={value}
                  className="relative inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-pressed:text-foreground"
                >
                  {active && (
                    <motion.span
                      layoutId={`${ids}-view`}
                      transition={SPRING}
                      aria-hidden
                      className="absolute inset-0 z-0 rounded-lg border border-(--studio-glass-border) bg-(--studio-glass-strong) shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)]"
                    />
                  )}
                  <span className="relative z-10 inline-flex items-center gap-1.5">
                    <Icon aria-hidden className="size-4" />
                    {t(`view.${value}`)}
                  </span>
                </Toggle>
              );
            })}
          </ToggleGroup>
        </div>
      </div>

      {search.query.isError ? (
        <StudioInlineError error={search.query.error} onRetry={() => search.query.refetch()} />
      ) : loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          <LoadingStatus label={tAll("shared.papers.loading")} />
          {Array.from({ length: 6 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
            <ShimmerSkeleton key={index} className="h-56 rounded-2xl" />
          ))}
        </div>
      ) : search.items.length === 0 && !search.yearRangeInvalid ? (
        filtered ? (
          <StudioStatePanel
            variant="section"
            headingLevel={2}
            icon={<SearchXIcon aria-hidden />}
            title={t("noMatch")}
            description={t("noMatchDescription")}
          >
            <button type="button" onClick={clearFilters} className={GHOST_BUTTON}>
              {t("clearFilters")}
            </button>
          </StudioStatePanel>
        ) : (
          <StudioStatePanel
            variant="section"
            headingLevel={2}
            icon={<LibraryIcon aria-hidden />}
            title={t("emptyTitle")}
            description={t("emptyDescription")}
          />
        )
      ) : search.items.length > 0 ? (
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={view}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={FADE}
            data-view={view}
          >
            {view === "grid" ? (
              <ul
                className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
                aria-label={t("resultsLabel")}
              >
                {search.items.map((item, index) => (
                  <li key={item.paper.paper_id} className="min-w-0">
                    <PaperCard item={item} index={index} />
                  </li>
                ))}
              </ul>
            ) : (
              <div className={cn(glassClassName(), "min-w-0 overflow-hidden px-1 sm:px-2")}>
                <PapersTable
                  papers={papers}
                  onSelect={(paper) => router.push(studioPaperPath(paper.paper_id))}
                  caption={t("resultsLabel")}
                />
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      ) : null}

      <Pager search={search} label={t("pager.label")} />
    </div>
  );
}

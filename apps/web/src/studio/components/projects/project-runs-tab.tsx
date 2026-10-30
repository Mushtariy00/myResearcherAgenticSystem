"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownIcon, ArrowUpDownIcon, ArrowUpIcon, HistoryIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";
import { listRunsOptions } from "@/client/@tanstack/react-query.gen";
import { toAmount, USD } from "@/lib/format";
import { isTerminalRunStatus } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { RunStatusPill } from "@/studio/components/dashboard/run-status-pill";
import { StudioSearchInput, StudioSelect } from "@/studio/components/dashboard/studio-fields";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { glassClassName } from "@/studio/lib/glass";
import { studioRunPath } from "@/studio/lib/nav";
import { GHOST_BUTTON, OUTLINE_BUTTON } from "@/studio/lib/ui";
import {
  DEFAULT_RUN_SORT,
  filterRuns,
  isRunFilter,
  nextSort,
  RUN_FILTERS,
  type RunFilter,
  type RunSort,
  type RunSortKey,
  sortRuns,
} from "./runs-filter";

const COLUMNS: readonly { key: RunSortKey; className?: string }[] = [
  { key: "topic", className: "w-full min-w-48" },
  { key: "status", className: "hidden sm:table-cell" },
  { key: "policy", className: "hidden md:table-cell" },
  { key: "cap", className: "hidden text-right md:table-cell" },
  { key: "created", className: "hidden lg:table-cell" },
];

/**
 * The project's runs as a sortable table with a topic search and a status filter (applied at
 * once, on what the project has). It refreshes every 15 s while a run is still in progress.
 * Narrow screens keep the topic and fold the status under it.
 */
export function ProjectRunsTab({
  projectId,
  onNewRun,
}: {
  projectId: string;
  /** Present when the user may start runs: the empty state offers the wizard. */
  onNewRun?: () => void;
}) {
  const t = useTranslations("studioWork.project.runs");
  const tRuns = useTranslations("project.runs");
  const tPolicies = useTranslations("project.newRun.policies");
  const format = useFormatter();
  const locale = useLocale();
  const ids = useId();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<RunFilter>("all");
  const [sort, setSort] = useState<RunSort>(DEFAULT_RUN_SORT);
  const runs = useQuery({
    ...listRunsOptions({ path: { project_id: projectId } }),
    refetchInterval: (current) =>
      current.state.data?.some((run) => !isTerminalRunStatus(run.status)) ? 15_000 : false,
  });

  const rows = useMemo(
    () => sortRuns(filterRuns(runs.data ?? [], query, filter), sort, locale),
    [runs.data, query, filter, sort, locale],
  );
  const headers: Record<RunSortKey, string> = {
    topic: tRuns("topic"),
    status: tRuns("status"),
    policy: tRuns("policy"),
    cap: tRuns("cap"),
    created: tRuns("created"),
  };

  if (runs.isPending) {
    return (
      <div className="grid gap-3" aria-busy="true">
        <LoadingStatus label={t("loading")} />
        <ShimmerSkeleton className="h-10 rounded-[10px]" />
        {Array.from({ length: 4 }, (_, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
          <ShimmerSkeleton key={index} className="h-14 rounded-xl" />
        ))}
      </div>
    );
  }
  if (runs.isError) {
    return <StudioInlineError error={runs.error} onRetry={() => runs.refetch()} />;
  }
  if (runs.data.length === 0) {
    return (
      <StudioStatePanel
        variant="section"
        headingLevel={3}
        icon={<HistoryIcon aria-hidden />}
        title={tRuns("empty")}
        description={onNewRun ? t("emptyCanStart") : t("emptyViewer")}
      >
        {onNewRun && (
          <button type="button" onClick={onNewRun} className={OUTLINE_BUTTON}>
            <PlusIcon aria-hidden />
            {t("startFirst")}
          </button>
        )}
      </StudioStatePanel>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="grid min-w-0 flex-1 gap-1.5">
          <label htmlFor={`${ids}-search`} className="text-xs font-medium text-muted-foreground">
            {t("search")}
          </label>
          <StudioSearchInput
            id={`${ids}-search`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("searchPlaceholder")}
            autoComplete="off"
          />
        </div>
        <div className="grid gap-1.5 sm:w-52">
          <label htmlFor={`${ids}-filter`} className="text-xs font-medium text-muted-foreground">
            {t("filter")}
          </label>
          <StudioSelect
            id={`${ids}-filter`}
            value={filter}
            onChange={(event) => {
              if (isRunFilter(event.target.value)) {
                setFilter(event.target.value);
              }
            }}
          >
            {RUN_FILTERS.map((value) => (
              <option key={value} value={value}>
                {t(`filters.${value}`)}
              </option>
            ))}
          </StudioSelect>
        </div>
      </div>

      <p className="text-xs text-muted-foreground tabular-nums" role="status">
        {t("showing", { shown: rows.length, total: runs.data.length })}
      </p>

      {rows.length === 0 ? (
        <div className="grid justify-items-center gap-3 rounded-2xl border border-dashed border-(--studio-glass-border) px-4 py-10 text-center">
          <p className="text-sm text-muted-foreground">{t("noMatch")}</p>
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setFilter("all");
            }}
            className={GHOST_BUTTON}
          >
            {t("clearFilters")}
          </button>
        </div>
      ) : (
        <div className={cn(glassClassName(), "overflow-x-auto")}>
          <table className="w-full text-sm">
            <caption className="sr-only">{t("caption")}</caption>
            <thead>
              <tr className="border-b border-(--studio-glass-border) text-left">
                {COLUMNS.map((column) => {
                  const sorted = sort.key === column.key ? (sort.desc ? "desc" : "asc") : false;
                  const Icon =
                    sorted === "asc"
                      ? ArrowUpIcon
                      : sorted === "desc"
                        ? ArrowDownIcon
                        : ArrowUpDownIcon;
                  return (
                    <th
                      key={column.key}
                      scope="col"
                      aria-sort={
                        sorted === "asc"
                          ? "ascending"
                          : sorted === "desc"
                            ? "descending"
                            : undefined
                      }
                      className={cn(
                        "px-3 py-2.5 text-xs font-medium whitespace-nowrap text-muted-foreground first:pl-4",
                        column.className,
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => setSort((current) => nextSort(current, column.key))}
                        className="inline-flex items-center gap-1 rounded-md outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        {headers[column.key]}
                        <Icon
                          aria-hidden
                          className={cn("size-3.5", sorted ? "text-foreground" : "opacity-50")}
                        />
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((run) => (
                <tr
                  key={run.id}
                  className="border-b border-(--studio-glass-border) transition-colors last:border-b-0 hover:bg-(--studio-hover)"
                >
                  <td className="px-3 py-3 align-top first:pl-4">
                    <div className="grid min-w-0 gap-1.5">
                      <Link
                        href={studioRunPath(run.id)}
                        className="line-clamp-2 w-fit rounded-sm font-medium text-foreground [overflow-wrap:anywhere] underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        {run.topic}
                      </Link>
                      <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground sm:hidden">
                        <RunStatusPill status={run.status} className="h-5" />
                        {format.dateTime(new Date(run.created_at), { dateStyle: "medium" })}
                      </span>
                    </div>
                  </td>
                  <td className="hidden px-3 py-3 align-top sm:table-cell">
                    <RunStatusPill status={run.status} />
                  </td>
                  <td className="hidden px-3 py-3 align-top whitespace-nowrap text-muted-foreground md:table-cell">
                    {tPolicies(`${run.llm_policy}.label`)}
                  </td>
                  <td className="hidden px-3 py-3 text-right align-top whitespace-nowrap tabular-nums md:table-cell">
                    {run.budget_cap_usd === null
                      ? tRuns("noCap")
                      : format.number(toAmount(run.budget_cap_usd), USD)}
                  </td>
                  <td className="hidden px-3 py-3 align-top whitespace-nowrap text-muted-foreground lg:table-cell">
                    {format.dateTime(new Date(run.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

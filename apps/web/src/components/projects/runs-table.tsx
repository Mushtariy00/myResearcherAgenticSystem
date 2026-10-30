"use client";

import { useQuery } from "@tanstack/react-query";
import {
  type ColumnFiltersState,
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createSortedRowModel,
  filterFn_equals,
  filterFn_includesString,
  globalFilteringFeature,
  metaHelper,
  rowSortingFeature,
  type SortingState,
  sortFn_basic,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import {
  ArrowDownIcon,
  ArrowUpDownIcon,
  ArrowUpIcon,
  HistoryIcon,
  PlayIcon,
  SearchIcon,
  XIcon,
} from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";
import type { RunOut, RunStatus } from "@/client";
import { listRunsOptions } from "@/client/@tanstack/react-query.gen";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { RunStatusBadge } from "@/components/app/status-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toAmount, USD } from "@/lib/format";
import { isRunStatus } from "@/lib/labels";
import { isTerminalRunStatus } from "@/lib/timeline";
import { cn } from "@/lib/utils";

/** Statuses in the order "sort by status" uses: what needs someone first, finished runs last. */
export const RUN_STATUS_ORDER = [
  "awaiting_approval",
  "running",
  "paused_budget",
  "queued",
  "failed",
  "rejected",
  "cancelled",
  "completed",
] as const satisfies readonly RunStatus[];

const STATUS_RANK = new Map<string, number>(
  RUN_STATUS_ORDER.map((status, index) => [status, index]),
);

/** The status filter's value for "every status". */
const ALL = "all";

/** While a run is still going, its status is refreshed this often. */
const ACTIVE_REFRESH_MS = 15_000;

/** Per-column classes: narrow screens hide the secondary columns. */
type ColumnMeta = { className?: string };

const features = tableFeatures({
  rowSortingFeature,
  columnFilteringFeature,
  globalFilteringFeature,
  sortedRowModel: createSortedRowModel(),
  filteredRowModel: createFilteredRowModel(),
  sortFns: { basic: sortFn_basic },
  filterFns: { equals: filterFn_equals, includesString: filterFn_includesString },
  columnMeta: metaHelper<ColumnMeta>(),
});

const helper = createColumnHelper<typeof features, RunOut>();

const DEFAULT_SORTING: SortingState = [{ id: "created", desc: true }];

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") {
    return <ArrowUpIcon aria-hidden className="size-3.5" />;
  }
  if (sorted === "desc") {
    return <ArrowDownIcon aria-hidden className="size-3.5" />;
  }
  return <ArrowUpDownIcon aria-hidden className="size-3.5 opacity-40" />;
}

export type RunsTableProps = {
  projectId: string;
  /** Owners, researchers and lab admins get a "New run" action in the empty state. */
  canStartRuns: boolean;
  newRunHref: string;
};

/**
 * A project's runs (newest first): search by topic, filter by status, sort by status or date.
 * Statuses refresh while a run is still in progress.
 */
export function RunsTable({ projectId, canStartRuns, newRunHref }: RunsTableProps) {
  const t = useTranslations("project.runs");
  const tStatus = useTranslations("runStatus");
  const tPolicy = useTranslations("project.newRun.policies");
  const format = useFormatter();
  const ids = useId();
  const runs = useQuery({
    ...listRunsOptions({ path: { project_id: projectId } }),
    refetchInterval: (query) =>
      query.state.data?.some((run) => !isTerminalRunStatus(run.status)) ? ACTIVE_REFRESH_MS : false,
  });
  const [sorting, setSorting] = useState<SortingState>(DEFAULT_SORTING);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [search, setSearch] = useState("");

  const columns = useMemo(
    () =>
      helper.columns([
        helper.accessor("topic", {
          header: t("topic"),
          enableSorting: false,
          meta: { className: "w-full min-w-48 whitespace-normal" },
        }),
        helper.accessor("status", {
          header: t("status"),
          filterFn: "equals",
          enableGlobalFilter: false,
          sortFn: (a, b) =>
            (STATUS_RANK.get(a.original.status) ?? RUN_STATUS_ORDER.length) -
            (STATUS_RANK.get(b.original.status) ?? RUN_STATUS_ORDER.length),
        }),
        helper.accessor("llm_policy", {
          header: t("policy"),
          enableSorting: false,
          enableGlobalFilter: false,
          meta: { className: "hidden sm:table-cell" },
        }),
        helper.accessor((run) => toAmount(run.budget_cap_usd), {
          id: "cap",
          header: t("cap"),
          enableSorting: false,
          enableGlobalFilter: false,
          meta: { className: "hidden text-right tabular-nums lg:table-cell" },
        }),
        helper.accessor((run) => Date.parse(run.created_at), {
          id: "created",
          header: t("created"),
          sortFn: "basic",
          sortDescFirst: true,
          enableGlobalFilter: false,
          meta: { className: "hidden md:table-cell" },
        }),
        helper.accessor((run) => Date.parse(run.updated_at), {
          id: "updated",
          header: t("updated"),
          sortFn: "basic",
          sortDescFirst: true,
          enableGlobalFilter: false,
        }),
      ]),
    [t],
  );

  const data = useMemo(() => runs.data ?? [], [runs.data]);
  const columnFilters = useMemo<ColumnFiltersState>(
    () => (status ? [{ id: "status", value: status }] : []),
    [status],
  );
  const table = useTable({
    features,
    columns,
    data,
    getRowId: (run) => run.id,
    state: { sorting, columnFilters, globalFilter: search.trim() || undefined },
    onSortingChange: setSorting,
    globalFilterFn: "includesString",
    enableSortingRemoval: false,
  });

  if (runs.isPending) {
    return <LoadingRows rows={4} />;
  }
  if (runs.isError) {
    return <QueryError error={runs.error} onRetry={() => runs.refetch()} />;
  }
  if (runs.data.length === 0) {
    return (
      <EmptyState
        icon={<HistoryIcon aria-hidden />}
        title={t("empty")}
        description={canStartRuns ? t("emptyDescription") : undefined}
        action={
          canStartRuns ? (
            <Link href={newRunHref} className={buttonVariants()}>
              <PlayIcon aria-hidden />
              {t("newRun")}
            </Link>
          ) : undefined
        }
      />
    );
  }

  const counts = new Map<string, number>();
  for (const run of runs.data) {
    counts.set(run.status, (counts.get(run.status) ?? 0) + 1);
  }
  const statusItems: Record<string, string> = {
    [ALL]: t("allStatuses", { count: runs.data.length }),
    ...Object.fromEntries(
      RUN_STATUS_ORDER.map((value) => [
        value,
        t("statusOption", { status: tStatus(value), count: counts.get(value) ?? 0 }),
      ]),
    ),
  };
  const rows = table.getRowModel().rows;
  const headerGroup = table.getHeaderGroups()[0];
  const filtered = status !== null || search.trim() !== "";
  const clearFilters = () => {
    setStatus(null);
    setSearch("");
  };

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-48 flex-1 gap-1.5">
          <Label htmlFor={`${ids}-search`}>{t("search")}</Label>
          <div className="relative">
            <SearchIcon
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              id={`${ids}-search`}
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("searchPlaceholder")}
              autoComplete="off"
              className="pl-8"
            />
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label id={`${ids}-status`}>{t("statusFilter")}</Label>
          <Select
            items={statusItems}
            value={status ?? ALL}
            onValueChange={(value) =>
              setStatus(typeof value === "string" && isRunStatus(value) ? value : null)
            }
          >
            <SelectTrigger className="w-56" aria-labelledby={`${ids}-status`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(statusItems).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {filtered && (
          <Button type="button" variant="ghost" onClick={clearFilters}>
            <XIcon aria-hidden />
            {t("clearFilters")}
          </Button>
        )}
      </div>
      <p className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
        {t("shown", { shown: rows.length, total: runs.data.length })}
      </p>
      <Table>
        <TableCaption className="sr-only">{t("caption")}</TableCaption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {headerGroup?.headers.map((header) => {
              const sorted = header.column.getIsSorted();
              const className = header.column.columnDef.meta?.className;
              return (
                <TableHead
                  key={header.id}
                  aria-sort={
                    sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined
                  }
                  className={cn("text-xs text-muted-foreground", className)}
                >
                  {header.column.getCanSort() ? (
                    <button
                      type="button"
                      onClick={header.column.getToggleSortingHandler()}
                      className="inline-flex items-center gap-1 rounded-sm font-medium outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <table.FlexRender header={header} />
                      <SortIcon sorted={sorted} />
                    </button>
                  ) : (
                    <table.FlexRender header={header} />
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={columns.length} className="py-8 text-center">
                <div className="flex flex-col items-center gap-2 text-muted-foreground">
                  <p>{t("noMatches")}</p>
                  <Button type="button" variant="outline" size="sm" onClick={clearFilters}>
                    {t("clearFilters")}
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => {
              const run = row.original;
              return (
                <TableRow key={row.id}>
                  {row.getAllCells().map((cell) => {
                    const className = cn("align-top", cell.column.columnDef.meta?.className);
                    switch (cell.column.id) {
                      case "topic":
                        return (
                          <TableCell key={cell.id} className={className}>
                            <Link
                              href={`/runs/${run.id}`}
                              className="line-clamp-2 font-medium break-words underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
                            >
                              {run.topic}
                            </Link>
                          </TableCell>
                        );
                      case "status":
                        return (
                          <TableCell key={cell.id} className={className}>
                            <RunStatusBadge status={run.status} />
                          </TableCell>
                        );
                      case "llm_policy":
                        return (
                          <TableCell key={cell.id} className={className}>
                            {tPolicy(`${run.llm_policy}.label`)}
                          </TableCell>
                        );
                      case "cap":
                        return (
                          <TableCell key={cell.id} className={className}>
                            {run.budget_cap_usd === null
                              ? t("noCap")
                              : format.number(toAmount(run.budget_cap_usd), USD)}
                          </TableCell>
                        );
                      case "created":
                      case "updated": {
                        const value =
                          cell.column.id === "created" ? run.created_at : run.updated_at;
                        return (
                          <TableCell
                            key={cell.id}
                            className={cn(className, "whitespace-nowrap text-muted-foreground")}
                          >
                            <time dateTime={value}>
                              {format.dateTime(new Date(value), {
                                dateStyle: "medium",
                                timeStyle: "short",
                              })}
                            </time>
                          </TableCell>
                        );
                      }
                      default:
                        return <TableCell key={cell.id} className={className} />;
                    }
                  })}
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </div>
  );
}

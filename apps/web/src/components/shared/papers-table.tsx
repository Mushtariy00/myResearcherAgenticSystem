"use client";

import {
  createColumnHelper,
  createSortedRowModel,
  metaHelper,
  rowSortingFeature,
  type SortingState,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import {
  ArrowDownIcon,
  ArrowUpDownIcon,
  ArrowUpIcon,
  FileCheckIcon,
  FileXIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { type KeyboardEvent, type ReactNode, useMemo, useRef, useState } from "react";
import type { PaperRef } from "@/client";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { authorNames } from "./format";

type Decision = PaperRef["decision"];

/** Per-column classes: container widths below a column's breakpoint hide it (see `@container`). */
type ColumnMeta = { className?: string };

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic },
  columnMeta: metaHelper<ColumnMeta>(),
});

const helper = createColumnHelper<typeof features, PaperRef>();

const DECISION_ORDER: Record<Decision, number> = { include: 0, maybe: 1, exclude: 2 };
const DECISION_TONES: Record<Decision, string> = {
  include: "success",
  maybe: "warning",
  exclude: "neutral",
};

const DEFAULT_SORTING: SortingState = [{ id: "relevance", desc: true }];
const SKELETON_ROWS = 5;

export type PapersTableProps = {
  papers: readonly PaperRef[];
  /** Shows placeholder rows (and marks the table busy) while papers load. */
  loading?: boolean;
  /** The paper shown elsewhere (viewer, details); its row is marked current. */
  selectedId?: string | null;
  /** Row click, or Enter/Space on the row's title; without it rows are not interactive. */
  onSelect?: (paper: PaperRef) => void;
  /** Table caption for screen readers (default "Papers"). */
  caption?: string;
  /** Message when there are no papers. */
  emptyMessage?: ReactNode;
  /** Initial sort; default: most relevant first. */
  defaultSorting?: SortingState;
  className?: string;
};

function DecisionBadge({ decision, reason }: { decision: Decision; reason?: string }) {
  const t = useTranslations("shared.papers.decisions");
  return (
    <span
      data-tone={DECISION_TONES[decision]}
      title={reason || undefined}
      className="inline-flex h-5 w-fit shrink-0 items-center rounded-full bg-(--tone)/15 px-2 text-xs font-medium whitespace-nowrap text-(--tone-fg)"
    >
      {t(decision)}
    </span>
  );
}

function PdfMark({ available }: { available: boolean }) {
  const t = useTranslations("shared.papers");
  const Icon = available ? FileCheckIcon : FileXIcon;
  return (
    <span
      className={cn(
        "inline-flex items-center",
        available ? "text-foreground" : "text-muted-foreground",
      )}
      title={available ? t("pdfAvailable") : t("pdfMissing")}
    >
      <Icon aria-hidden className="size-4" />
      <span className="sr-only">{available ? t("pdfAvailable") : t("pdfMissing")}</span>
    </span>
  );
}

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") {
    return <ArrowUpIcon aria-hidden className="size-3.5" />;
  }
  if (sorted === "desc") {
    return <ArrowDownIcon aria-hidden className="size-3.5" />;
  }
  return <ArrowUpDownIcon aria-hidden className="size-3.5 opacity-40" />;
}

/**
 * Papers from a literature output: title with authors, venue and year; relevance as a bar;
 * screening decision; citations; source; PDF availability. Columns sort from their headers.
 * Narrow containers keep the title and relevance columns and fold the decision and PDF marks
 * under the title. Rows are selectable by click and by keyboard: the titles form one tab stop,
 * arrow keys (and Home/End) move between rows, Enter or Space selects.
 */
export function PapersTable({
  papers,
  loading = false,
  selectedId,
  onSelect,
  caption,
  emptyMessage,
  defaultSorting = DEFAULT_SORTING,
  className,
}: PapersTableProps) {
  const t = useTranslations("shared.papers");
  const format = useFormatter();
  const titleButtons = useRef(new Map<string, HTMLButtonElement>());
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const interactive = onSelect !== undefined;

  const columns = useMemo(
    () =>
      helper.columns([
        helper.accessor("title", {
          header: t("columns.title"),
          sortFn: "alphanumeric",
          meta: { className: "w-full min-w-48 whitespace-normal" },
        }),
        helper.accessor("relevance", {
          header: t("columns.relevance"),
          sortFn: "basic",
          sortDescFirst: true,
          meta: { className: "w-24 @md:w-32" },
        }),
        helper.accessor("decision", {
          header: t("columns.decision"),
          sortFn: (a, b) =>
            DECISION_ORDER[a.original.decision] - DECISION_ORDER[b.original.decision],
          meta: { className: "hidden @xl:table-cell" },
        }),
        helper.accessor("year", {
          header: t("columns.year"),
          sortFn: "basic",
          sortDescFirst: true,
          meta: { className: "hidden text-right tabular-nums @2xl:table-cell" },
        }),
        helper.accessor((paper) => paper.citation_count ?? undefined, {
          id: "citations",
          header: t("columns.citations"),
          sortFn: "basic",
          sortDescFirst: true,
          sortUndefined: "last",
          meta: { className: "hidden text-right tabular-nums @3xl:table-cell" },
        }),
        helper.accessor("source", {
          header: t("columns.source"),
          sortFn: "alphanumeric",
          meta: { className: "hidden @4xl:table-cell" },
        }),
        helper.accessor("pdf_available", {
          header: t("columns.pdf"),
          sortFn: (a, b) => Number(b.original.pdf_available) - Number(a.original.pdf_available),
          meta: { className: "hidden text-center @xl:table-cell" },
        }),
      ]),
    [t],
  );

  const data = useMemo(() => [...papers], [papers]);
  const table = useTable({
    features,
    columns,
    data,
    getRowId: (paper) => paper.paper_id,
    initialState: { sorting: defaultSorting },
    enableSortingRemoval: false,
  });
  const rows = table.getRowModel().rows;
  const headerGroup = table.getHeaderGroups()[0];
  const columnCount = columns.length;

  // One tab stop: the focused row, else the selected one, else the first.
  const tabStopId =
    rows.find((row) => row.id === focusedId)?.id ??
    rows.find((row) => row.id === selectedId)?.id ??
    rows[0]?.id;

  function focusRow(id: string | undefined) {
    if (!id) {
      return;
    }
    setFocusedId(id);
    titleButtons.current.get(id)?.focus();
  }

  function onRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, index: number, id: string) {
    if (event.target !== titleButtons.current.get(id)) {
      return;
    }
    const target =
      event.key === "ArrowDown"
        ? rows[Math.min(index + 1, rows.length - 1)]
        : event.key === "ArrowUp"
          ? rows[Math.max(index - 1, 0)]
          : event.key === "Home"
            ? rows[0]
            : event.key === "End"
              ? rows[rows.length - 1]
              : undefined;
    if (target) {
      event.preventDefault();
      focusRow(target.id);
    }
  }

  function renderCell(columnId: string, paper: PaperRef, isTabStop: boolean, selected: boolean) {
    switch (columnId) {
      case "title": {
        const { names, truncated } = authorNames(paper.authors);
        const authors = names ? (truncated ? t("etAl", { names }) : names) : t("unknownAuthors");
        return (
          <div className="grid min-w-0 gap-0.5">
            {interactive ? (
              <button
                type="button"
                ref={(element) => {
                  if (element) {
                    titleButtons.current.set(paper.paper_id, element);
                  } else {
                    titleButtons.current.delete(paper.paper_id);
                  }
                }}
                tabIndex={isTabStop ? 0 : -1}
                aria-current={selected ? "true" : undefined}
                onFocus={() => setFocusedId(paper.paper_id)}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect?.(paper);
                }}
                className="w-fit rounded-sm text-left font-medium break-words outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {paper.title}
              </button>
            ) : (
              <span className="font-medium break-words">{paper.title}</span>
            )}
            <span className="text-xs break-words text-muted-foreground">
              {authors}
              {paper.venue && <> · {paper.venue}</>}
              <span className="@2xl:hidden"> · {paper.year}</span>
            </span>
            <span className="flex items-center gap-2 pt-0.5 @xl:hidden">
              <DecisionBadge decision={paper.decision} reason={paper.decision_reason} />
              <PdfMark available={paper.pdf_available} />
            </span>
          </div>
        );
      }
      case "relevance": {
        const share = Math.min(1, Math.max(0, paper.relevance));
        return (
          <div className="flex items-center gap-2" data-stage="literature">
            <span aria-hidden className="h-1.5 w-10 overflow-hidden rounded-full bg-muted @md:w-16">
              <span
                className="block h-full rounded-full bg-(--tone)"
                style={{ width: `${share * 100}%` }}
              />
            </span>
            <span className="text-xs tabular-nums">
              {format.number(paper.relevance, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
          </div>
        );
      }
      case "decision":
        return <DecisionBadge decision={paper.decision} reason={paper.decision_reason} />;
      case "year":
        return paper.year;
      case "citations":
        return paper.citation_count === null || paper.citation_count === undefined ? (
          <>
            <span aria-hidden>—</span>
            <span className="sr-only">{t("unknown")}</span>
          </>
        ) : (
          format.number(paper.citation_count)
        );
      case "source":
        return t(`sources.${paper.source}`);
      case "pdf_available":
        return <PdfMark available={paper.pdf_available} />;
      default:
        return null;
    }
  }

  return (
    <div data-slot="papers-table" className={cn("@container w-full", className)}>
      <Table aria-busy={loading || undefined}>
        <TableCaption className="sr-only">{caption ?? t("caption")}</TableCaption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {headerGroup?.headers.map((header) => {
              const sorted = header.column.getIsSorted();
              const meta = header.column.columnDef.meta;
              return (
                <TableHead
                  key={header.id}
                  aria-sort={
                    sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined
                  }
                  className={cn("text-xs text-muted-foreground", meta?.className)}
                >
                  <button
                    type="button"
                    onClick={header.column.getToggleSortingHandler()}
                    className="inline-flex items-center gap-1 rounded-sm font-medium outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <table.FlexRender header={header} />
                    <SortIcon sorted={sorted} />
                  </button>
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            Array.from({ length: SKELETON_ROWS }, (_, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
              <TableRow key={index} className="hover:bg-transparent">
                {headerGroup?.headers.map((header) => (
                  <TableCell key={header.id} className={header.column.columnDef.meta?.className}>
                    <Skeleton className="h-4 w-full" />
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : rows.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={columnCount} className="py-8 text-center text-muted-foreground">
                {emptyMessage ?? t("empty")}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row, index) => {
              const selected = row.id === selectedId;
              return (
                <TableRow
                  key={row.id}
                  data-state={selected ? "selected" : undefined}
                  onClick={interactive ? () => onSelect?.(row.original) : undefined}
                  onKeyDown={
                    interactive ? (event) => onRowKeyDown(event, index, row.id) : undefined
                  }
                  className={cn(interactive && "cursor-pointer")}
                >
                  {row.getAllCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn("align-top", cell.column.columnDef.meta?.className)}
                    >
                      {renderCell(cell.column.id, row.original, row.id === tabStopId, selected)}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
      {loading && (
        <p className="sr-only" role="status">
          {t("loading")}
        </p>
      )}
    </div>
  );
}

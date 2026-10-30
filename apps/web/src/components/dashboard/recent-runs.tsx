"use client";

import { HistoryIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useId } from "react";
import type { RecentRunOut } from "@/client";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { RunStatusBadge } from "@/components/app/status-badge";
import { projectHref } from "@/components/projects/project-tabs";
import { StageIcon } from "@/components/shared/stage-icon";
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
import { useRecentRuns } from "@/hooks/use-recent-runs";
import { isTerminalRunStatus } from "@/lib/timeline";
import { useCurrentStage, useRefetchWhile, useStageName } from "./run-stage";

/** Runs the dashboard lists. */
export const RECENT_LIMIT = 10;

/** While a listed run is in progress, statuses are refreshed this often. */
const RECENT_REFRESH_MS = 30_000;

function StageCell({ run }: { run: RecentRunOut }) {
  const t = useTranslations("dashboard.recentRuns");
  const stageName = useStageName();
  const { stage, loading } = useCurrentStage(run);
  if (stage) {
    return (
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
        <StageIcon stage={stage} />
        {stageName(stage)}
      </span>
    );
  }
  if (loading) {
    return (
      <>
        <Skeleton className="h-4 w-20" />
        <span className="sr-only">{t("stageLoading")}</span>
      </>
    );
  }
  return (
    <span className="text-muted-foreground">
      <span aria-hidden>—</span>
      <span className="sr-only">
        {isTerminalRunStatus(run.status) ? t("finished") : t("noStage")}
      </span>
    </span>
  );
}

function RecentRunRow({ run }: { run: RecentRunOut }) {
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const updated = new Date(run.updated_at);
  return (
    <TableRow>
      <TableCell className="max-w-72 align-top whitespace-normal">
        <Link
          href={`/runs/${run.id}`}
          className="line-clamp-2 font-medium break-words underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
        >
          {run.topic}
        </Link>
        <span className="block truncate text-xs text-muted-foreground sm:hidden">
          {run.project_name}
        </span>
      </TableCell>
      <TableCell className="hidden max-w-48 align-top sm:table-cell">
        <Link
          href={projectHref(run.project_id)}
          className="block truncate text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:underline focus-visible:outline-none"
        >
          {run.project_name}
        </Link>
      </TableCell>
      <TableCell className="align-top">
        <RunStatusBadge status={run.status} />
      </TableCell>
      <TableCell className="hidden align-top md:table-cell">
        <StageCell run={run} />
      </TableCell>
      <TableCell className="align-top whitespace-nowrap text-muted-foreground">
        <time
          dateTime={run.updated_at}
          title={format.dateTime(updated, { dateStyle: "medium", timeStyle: "short" })}
        >
          {format.relativeTime(updated, now)}
        </time>
      </TableCell>
    </TableRow>
  );
}

/** The newest runs across the user's projects, with where each one is in the pipeline. */
export function RecentRuns() {
  const t = useTranslations("dashboard.recentRuns");
  const headingId = useId();
  const runs = useRecentRuns(RECENT_LIMIT);
  const active = runs.data?.some((run) => !isTerminalRunStatus(run.status)) ?? false;
  useRefetchWhile(active, runs.refetch, RECENT_REFRESH_MS);

  return (
    <section aria-labelledby={headingId} className="grid gap-3">
      <h2 id={headingId} className="text-base font-semibold">
        {t("title")}
      </h2>
      {runs.isPending ? (
        <LoadingRows rows={3} />
      ) : runs.isError ? (
        <QueryError error={runs.error} onRetry={() => runs.refetch()} />
      ) : runs.data.length === 0 ? (
        <EmptyState
          icon={<HistoryIcon aria-hidden />}
          title={t("empty")}
          description={t("emptyDescription")}
        />
      ) : (
        <div className="rounded-xl border bg-card px-2">
          <Table>
            <TableCaption className="sr-only">{t("caption")}</TableCaption>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>{t("columns.topic")}</TableHead>
                <TableHead className="hidden sm:table-cell">{t("columns.project")}</TableHead>
                <TableHead>{t("columns.status")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("columns.stage")}</TableHead>
                <TableHead>{t("columns.updated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data.map((run) => (
                <RecentRunRow key={run.id} run={run} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}

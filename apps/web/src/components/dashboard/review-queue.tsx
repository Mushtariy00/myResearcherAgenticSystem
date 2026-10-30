"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleCheckIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useId } from "react";
import type { RecentRunOut } from "@/client";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { canSteerRun } from "@/components/projects/permissions";
import { projectHref } from "@/components/projects/project-tabs";
import { StageIcon } from "@/components/shared/stage-icon";
import { buttonVariants } from "@/components/ui/button";
import { useRecentRuns } from "@/hooks/use-recent-runs";
import { cn } from "@/lib/utils";
import { useCurrentStage, useRefetchWhile, useStageName } from "./run-stage";

/** Awaiting runs fetched for the queue (the API's newest first). */
export const REVIEW_LIMIT = 20;

/** The queue changes whenever an output is ready somewhere: look again this often. */
const REVIEW_REFRESH_MS = 30_000;

function ReviewItem({ run }: { run: RecentRunOut }) {
  const t = useTranslations("dashboard.review");
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const stageName = useStageName();
  const { stage, loading } = useCurrentStage(run);
  const updated = new Date(run.updated_at);

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3">
      <span
        data-stage={stage ?? undefined}
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-lg",
          stage ? "bg-(--tone)/15" : "bg-muted",
        )}
      >
        <StageIcon stage={stage ?? ""} />
      </span>
      <div className="grid min-w-0 flex-1 gap-0.5">
        <p className="line-clamp-2 font-medium break-words">{run.topic}</p>
        <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
          <Link
            href={projectHref(run.project_id)}
            className="underline-offset-4 hover:text-foreground hover:underline focus-visible:underline focus-visible:outline-none"
          >
            {run.project_name}
          </Link>
          <span aria-hidden>·</span>
          <span>
            {stage
              ? t("stageReady", { stage: stageName(stage) })
              : loading
                ? t("stageLoading")
                : t("outputReady")}
          </span>
          <span aria-hidden>·</span>
          <time
            dateTime={run.updated_at}
            title={format.dateTime(updated, { dateStyle: "medium", timeStyle: "short" })}
          >
            {t("ready", { time: format.relativeTime(updated, now) })}
          </time>
        </p>
      </div>
      <Link
        href={`/runs/${run.id}`}
        className={buttonVariants({ size: "sm" })}
        aria-label={t("reviewLabel", { topic: run.topic })}
      >
        {t("review")}
      </Link>
    </li>
  );
}

/**
 * Runs waiting for a decision the user may make: every awaiting run for lab admins, a project's
 * awaiting runs for its owners, and their own for researchers (the API's `can_steer`).
 */
export function ReviewQueue() {
  const t = useTranslations("dashboard.review");
  const headingId = useId();
  const user = useCurrentUser();
  const runs = useRecentRuns(REVIEW_LIMIT, "awaiting_approval");
  // Roles decide which awaiting runs are the user's to review (the dashboard lists projects too).
  const projects = useQuery(listProjectsOptions());
  useRefetchWhile(true, runs.refetch, REVIEW_REFRESH_MS);

  const needsRoles = user.role !== "admin";
  const roles = new Map((projects.data ?? []).map((project) => [project.id, project.my_role]));
  const items = (runs.data ?? []).filter((run) =>
    canSteerRun(user, roles.get(run.project_id), run),
  );
  const pending = runs.isPending || (needsRoles && projects.isPending);
  const error = runs.isError ? runs.error : needsRoles && projects.isError ? projects.error : null;

  return (
    <section aria-labelledby={headingId} className="grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={headingId} className="text-base font-semibold">
          {t("title")}
          {items.length > 0 && (
            <>
              <span
                aria-hidden
                className="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-medium text-primary-foreground tabular-nums"
              >
                {items.length}
              </span>
              <span className="sr-only">, {t("count", { count: items.length })}</span>
            </>
          )}
        </h2>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>
      {pending ? (
        <LoadingRows rows={2} />
      ) : error ? (
        <QueryError
          error={error}
          onRetry={() => {
            void runs.refetch();
            void projects.refetch();
          }}
        />
      ) : items.length === 0 ? (
        <p className="flex items-center gap-2 rounded-xl border border-dashed px-4 py-5 text-sm text-muted-foreground">
          <CircleCheckIcon aria-hidden className="size-4 shrink-0" />
          {t("empty")}
        </p>
      ) : (
        <ul className="grid gap-2">
          {items.map((run) => (
            <ReviewItem key={run.id} run={run} />
          ))}
        </ul>
      )}
    </section>
  );
}

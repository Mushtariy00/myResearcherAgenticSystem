"use client";

import { useQuery } from "@tanstack/react-query";
import { CoinsIcon, EyeIcon, FolderOpenIcon, SparklesIcon, WorkflowIcon } from "lucide-react";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { canCreateProjects } from "@/components/projects/permissions";
import { useNotifications } from "@/hooks/use-notifications";
import { RECENT_RUNS_LIMIT, useRecentRuns } from "@/hooks/use-recent-runs";
import { USAGE_DAYS, useUsage } from "@/hooks/use-usage";
import { TIME_ZONE } from "@/i18n/config";
import { USD } from "@/lib/format";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { TiltCard } from "@/studio/components/effects/tilt-card";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { CreateProjectDialog } from "./create-project-dialog";
import {
  countPerDay,
  isActiveRun,
  reviewQueue,
  summarizeRuns,
  summarizeUsage,
  TREND_DAYS,
} from "./dashboard-data";
import { GpuCard } from "./gpu-card";
import { KpiTile } from "./kpi-tile";
import { ProjectCard } from "./project-card";
import { RecentRuns } from "./recent-runs";
import { ReviewList } from "./review-list";
import { SpendChart } from "./spend-chart";
import { StudioInlineError } from "./studio-panel";

type PartOfDay = "morning" | "afternoon" | "evening";

/** The lab works in Korea: the greeting follows the app's time zone, as dates do. */
function partOfDay(date: Date): PartOfDay {
  const hour = Number(
    new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: TIME_ZONE,
    }).format(date),
  );
  if (hour >= 5 && hour < 12) {
    return "morning";
  }
  return hour >= 12 && hour < 18 ? "afternoon" : "evening";
}

/**
 * The Studio dashboard, on the same hooks as Classic: a greeting; four live metrics with
 * sparklines (active runs, outputs awaiting your review, this month's paid spend, today's free
 * calls); the review queue with each run's pipeline; recent runs; the lab GPU; 30 days of spend;
 * and the projects. A metric whose source fails says so and offers a retry; nothing is guessed.
 */
export function StudioDashboard() {
  const t = useTranslations("studioWork.dashboard");
  const tAll = useTranslations();
  const format = useFormatter();
  const user = useCurrentUser();
  const [today] = useState(() => new Date());
  const now = useNow({ updateInterval: 60_000 });
  const projects = useQuery(listProjectsOptions());
  const runs = useRecentRuns(RECENT_RUNS_LIMIT.max);
  const notifications = useNotifications();
  const usage = useUsage("me", USAGE_DAYS.default);
  const name = user.name || user.email;

  const runSummary = useMemo(
    () => (runs.data ? summarizeRuns(runs.data, now) : null),
    [runs.data, now],
  );
  const queue = useMemo(
    () =>
      notifications.query.data
        ? reviewQueue(notifications.query.data.items, runs.data ?? [])
        : null,
    [notifications.query.data, runs.data],
  );
  const reviewTrend = useMemo(
    () =>
      queue
        ? countPerDay(
            queue.map((item) => item.readyAt),
            TREND_DAYS,
            now,
          )
        : null,
    [queue, now],
  );
  const spend = useMemo(
    () => (usage.data ? summarizeUsage(usage.data, now) : null),
    [usage.data, now],
  );
  const activeByProject = useMemo(() => {
    const counts = new Map<string, number>();
    for (const run of runs.data ?? []) {
      if (isActiveRun(run.status)) {
        counts.set(run.project_id, (counts.get(run.project_id) ?? 0) + 1);
      }
    }
    return counts;
  }, [runs.data]);
  const expiring = queue?.filter((item) => item.expiring).length ?? 0;
  const failed = (onRetry: () => void) => ({
    message: t("kpi.failed"),
    retryLabel: tAll("common.retry"),
    onRetry,
  });

  return (
    <div className="grid gap-8 lg:gap-10">
      <header className="studio-rise grid min-w-0 gap-2">
        <p className="text-sm text-muted-foreground" suppressHydrationWarning>
          {format.dateTime(today, { weekday: "long", month: "long", day: "numeric" })}
        </p>
        <h1
          className="studio-display min-w-0 text-3xl text-foreground [overflow-wrap:anywhere] sm:text-4xl"
          suppressHydrationWarning
        >
          {t(`greeting.${partOfDay(today)}`, { name })}
        </h1>
        <p className="text-base text-pretty text-muted-foreground">{t("subtitle")}</p>
      </header>

      <section aria-labelledby="studio-overview-title" className="grid gap-4">
        <h2 id="studio-overview-title" className="sr-only">
          {t("overview")}
        </h2>
        <div className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-2 sm:gap-4 xl:grid-cols-4">
          <KpiTile
            label={t("kpi.active")}
            icon={WorkflowIcon}
            tone="info"
            value={runSummary?.active ?? null}
            trend={runSummary?.startedPerDay}
            hint={runSummary ? t("kpi.activeHint", { count: runSummary.startedInTrend }) : null}
            failed={runs.isError ? failed(() => runs.refetch()) : null}
          />
          <KpiTile
            label={t("kpi.review")}
            icon={EyeIcon}
            tone="warning"
            value={queue?.length ?? null}
            trend={reviewTrend}
            hint={
              queue
                ? expiring > 0
                  ? t("kpi.reviewExpiring", { count: expiring })
                  : t("kpi.reviewHint")
                : null
            }
            failed={
              notifications.query.isError ? failed(() => notifications.query.refetch()) : null
            }
          />
          <KpiTile
            label={t("kpi.spend")}
            icon={CoinsIcon}
            tone="success"
            value={spend?.spentThisMonth ?? null}
            format={USD}
            trend={spend?.days.map((day) => day.paidUsd)}
            hint={
              spend
                ? spend.budget <= 0
                  ? tAll("budget.noBudget")
                  : t("kpi.spendHint", {
                      percent: format.number(Math.round(spend.percentUsed)),
                      budget: format.number(spend.budget, USD),
                    })
                : null
            }
            failed={usage.isError ? failed(() => usage.refetch()) : null}
          >
            {spend && spend.budget > 0 && (
              <div
                role="progressbar"
                aria-label={tAll("budget.used")}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(spend.percentUsed)}
                className="h-1.5 w-full overflow-hidden rounded-full bg-[color-mix(in_oklch,var(--foreground)_10%,transparent)]"
              >
                <div
                  data-tone={
                    spend.percentUsed >= 100
                      ? "danger"
                      : spend.percentUsed >= 80
                        ? "warning"
                        : "success"
                  }
                  className="h-full origin-left rounded-full bg-(--tone) transition-transform duration-700 ease-out motion-reduce:transition-none"
                  style={{ transform: `scaleX(${spend.percentUsed / 100})` }}
                />
              </div>
            )}
          </KpiTile>
          <KpiTile
            label={t("kpi.freeCalls")}
            icon={SparklesIcon}
            tone="neutral"
            value={spend?.freeCallsToday ?? null}
            trend={spend?.days.map((day) => day.freeCalls)}
            hint={spend ? t("kpi.freeCallsHint", { paid: spend.paidCallsToday }) : null}
            failed={usage.isError ? failed(() => usage.refetch()) : null}
          />
        </div>
      </section>

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
        <ReviewList
          className="lg:col-span-2"
          items={queue ?? []}
          loading={notifications.query.isPending || runs.isPending}
          error={notifications.query.isError ? notifications.query.error : null}
          onRetry={() => notifications.query.refetch()}
        />
        <GpuCard />
        <SpendChart
          className="lg:col-span-2"
          days={spend?.days ?? []}
          total={spend?.paidInWindow ?? 0}
          demo={usage.data?.demo ?? false}
          loading={usage.isPending}
          error={usage.isError ? usage.error : null}
          onRetry={() => usage.refetch()}
        />
        <RecentRuns
          runs={runs.data ?? []}
          loading={runs.isPending}
          error={runs.isError ? runs.error : null}
          onRetry={() => runs.refetch()}
        />
      </div>

      <section
        id="projects"
        aria-labelledby="studio-projects-title"
        aria-busy={projects.isPending}
        className="grid scroll-mt-24 gap-4"
      >
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <h2
              id="studio-projects-title"
              className="studio-display text-xl text-foreground sm:text-2xl"
            >
              {t("projects.title")}
            </h2>
            {projects.data && projects.data.length > 0 && (
              <p className="text-sm text-muted-foreground tabular-nums">
                {t("projects.count", { count: projects.data.length })}
              </p>
            )}
          </div>
          {canCreateProjects(user) && <CreateProjectDialog />}
        </div>
        {projects.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <LoadingStatus label={tAll("common.loading")} />
            {Array.from({ length: 3 }, (_, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
              <ShimmerSkeleton key={index} className="h-40 rounded-2xl" />
            ))}
          </div>
        ) : projects.isError ? (
          <StudioInlineError error={projects.error} onRetry={() => projects.refetch()} />
        ) : projects.data.length === 0 ? (
          <StudioStatePanel
            variant="section"
            headingLevel={3}
            icon={<FolderOpenIcon aria-hidden />}
            title={tAll("dashboard.emptyTitle")}
            description={
              canCreateProjects(user)
                ? tAll("dashboard.emptyDescription")
                : tAll("dashboard.emptyDescriptionMember")
            }
          />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects.data.map((project, index) => (
              <li key={project.id} className="min-w-0">
                <TiltCard maxTilt={3} className="h-full">
                  <ProjectCard
                    project={project}
                    index={index}
                    activeRuns={activeByProject.get(project.id) ?? 0}
                  />
                </TiltCard>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

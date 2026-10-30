"use client";

import { useQuery } from "@tanstack/react-query";
import { BellIcon, CoinsIcon, FolderKanbanIcon, FolderOpenIcon, WalletIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { getMeOptions, listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { QueryError } from "@/components/app/query-state";
import { TIME_ZONE } from "@/i18n/config";
import { percentUsed, toAmount, USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { useUnreadNotifications } from "@/studio/hooks/use-unread-notifications";
import { KpiTile } from "./kpi-tile";
import { ProjectCard } from "./project-card";

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
 * The first Studio dashboard: a greeting, metrics the API provides today (projects, this month's
 * paid spend and what is left of the budget, unread notifications) and the project list. A
 * metric the API cannot provide is left out rather than estimated.
 */
export function StudioDashboard() {
  const t = useTranslations();
  const format = useFormatter();
  const user = useCurrentUser();
  const me = useQuery(getMeOptions());
  const projects = useQuery(listProjectsOptions());
  const unread = useUnreadNotifications();
  const [now] = useState(() => new Date());
  const name = user.name || user.email;

  const budget = me.data ? toAmount(me.data.budget_usd) : null;
  const spent = me.data ? toAmount(me.data.spent_usd) : null;
  const left = budget !== null && spent !== null ? Math.max(0, budget - spent) : null;
  const used = budget !== null && spent !== null ? percentUsed(spent, budget) : 0;

  return (
    <div className="grid gap-10 lg:gap-12">
      <header className="studio-rise grid gap-2">
        <p className="text-sm text-muted-foreground" suppressHydrationWarning>
          {format.dateTime(now, { weekday: "long", month: "long", day: "numeric" })}
        </p>
        <h1
          className="studio-display text-3xl text-foreground sm:text-4xl"
          suppressHydrationWarning
        >
          {t(`studio.dashboard.greeting.${partOfDay(now)}`, { name })}
        </h1>
        <p className="text-base text-muted-foreground">{t("studio.dashboard.subtitle")}</p>
      </header>

      <section aria-labelledby="studio-overview-title" className="grid gap-4">
        <h2 id="studio-overview-title" className="sr-only">
          {t("studio.dashboard.overview")}
        </h2>
        {me.isError && <QueryError error={me.error} onRetry={() => me.refetch()} />}
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          <KpiTile
            label={t("studio.dashboard.kpi.projects")}
            icon={FolderKanbanIcon}
            tone="info"
            value={projects.data ? projects.data.length : null}
            hint={t("studio.dashboard.kpi.projectsHint")}
          />
          {!me.isError && (
            <KpiTile
              label={t("studio.dashboard.kpi.spent")}
              icon={CoinsIcon}
              tone="warning"
              value={spent}
              format={USD}
              hint={t("budget.description")}
            />
          )}
          {!me.isError && (
            <KpiTile
              label={t("studio.dashboard.kpi.left")}
              icon={WalletIcon}
              tone="success"
              value={left}
              format={USD}
              hint={
                budget === null
                  ? null
                  : budget <= 0
                    ? t("budget.noBudget")
                    : t("studio.dashboard.kpi.leftHint", {
                        percent: format.number(Math.round(used)),
                        budget: format.number(budget, USD),
                      })
              }
            >
              {budget !== null && budget > 0 && (
                <div
                  role="progressbar"
                  aria-label={t("budget.used")}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(used)}
                  className="h-1.5 w-full overflow-hidden rounded-full bg-(--studio-glass-strong)"
                >
                  <div
                    data-tone={used >= 100 ? "danger" : used >= 80 ? "warning" : "success"}
                    className="h-full origin-left rounded-full bg-(--tone) transition-transform duration-700 ease-out motion-reduce:transition-none"
                    style={{ transform: `scaleX(${used / 100})` }}
                  />
                </div>
              )}
            </KpiTile>
          )}
          {!unread.unavailable && (
            <KpiTile
              label={t("studio.dashboard.kpi.unread")}
              icon={BellIcon}
              tone="info"
              value={unread.count}
              hint={t("studio.dashboard.kpi.unreadHint")}
            />
          )}
        </div>
      </section>

      <section
        id="projects"
        aria-labelledby="studio-projects-title"
        aria-busy={projects.isPending}
        className="grid scroll-mt-24 gap-4"
      >
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2
            id="studio-projects-title"
            className="studio-display text-xl text-foreground sm:text-2xl"
          >
            {t("studio.dashboard.projects.title")}
          </h2>
          {projects.data && projects.data.length > 0 && (
            <p className="text-sm text-muted-foreground tabular-nums">
              {t("studio.dashboard.projects.count", { count: projects.data.length })}
            </p>
          )}
        </div>
        {projects.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <LoadingStatus label={t("common.loading")} />
            {Array.from({ length: 3 }, (_, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
              <ShimmerSkeleton key={index} className={cn("h-40 rounded-2xl")} />
            ))}
          </div>
        ) : projects.isError ? (
          <QueryError error={projects.error} onRetry={() => projects.refetch()} />
        ) : projects.data.length === 0 ? (
          <StudioStatePanel
            variant="section"
            headingLevel={3}
            icon={<FolderOpenIcon aria-hidden />}
            title={t("dashboard.emptyTitle")}
            description={t("dashboard.emptyDescription")}
          />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects.data.map((project, index) => (
              <li key={project.id} className="min-w-0">
                <ProjectCard project={project} index={index} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

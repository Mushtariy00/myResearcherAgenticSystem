"use client";

import { useTranslations } from "next-intl";
import { useCurrentUser } from "@/components/app/current-user";
import { PageHeader } from "@/components/app/query-state";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { canCreateProjects } from "@/components/projects/permissions";
import { GpuWidget } from "./gpu-widget";
import { ProjectList } from "./project-list";
import { RecentRuns } from "./recent-runs";
import { ReviewQueue } from "./review-queue";
import { SpendWidget } from "./spend-widget";

/**
 * The Classic home page: what waits for the user's review, the newest runs, their projects,
 * and beside them the lab GPU and their own spend.
 */
export function Dashboard() {
  const t = useTranslations("dashboard");
  const user = useCurrentUser();

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("welcome", { name: user.name || user.email })}
        actions={canCreateProjects(user) ? <CreateProjectDialog /> : undefined}
      />
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="grid min-w-0 content-start gap-8">
          <ReviewQueue />
          <RecentRuns />
          <ProjectList />
        </div>
        <aside aria-label={t("resources")} className="grid min-w-0 content-start gap-6">
          <GpuWidget />
          <SpendWidget />
        </aside>
      </div>
    </>
  );
}

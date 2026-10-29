"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeftIcon, LockIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { getProjectOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { MembersCard } from "./members-card";
import { NewRunCard } from "./new-run-card";
import { RunsCard } from "./runs-card";

export function ProjectView({ projectId }: { projectId: string }) {
  const t = useTranslations("project");
  const user = useCurrentUser();
  const project = useQuery(getProjectOptions({ path: { project_id: projectId } }));

  const back = (
    <Link
      href="/"
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ChevronLeftIcon className="size-4" aria-hidden />
      {t("back")}
    </Link>
  );

  if (project.isPending) {
    return (
      <>
        {back}
        <LoadingRows rows={4} />
      </>
    );
  }
  if (project.isError) {
    return (
      <>
        {back}
        <QueryError error={project.error} onRetry={() => project.refetch()} />
      </>
    );
  }

  const isAdmin = user.role === "admin";
  const role = project.data.my_role;
  // Permissions (docs/PLAN.md): owners and researchers start runs; owners manage members.
  const canStartRuns = isAdmin || role === "owner" || role === "researcher";
  const canManageMembers = isAdmin || role === "owner";

  return (
    <>
      {back}
      <PageHeader title={project.data.name} description={project.data.description || undefined}>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <RoleBadge role={role ?? (isAdmin ? "admin" : null)} />
          {project.data.privacy === "confidential" && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <LockIcon className="size-3" aria-hidden />
              {t("confidential")}
            </span>
          )}
        </div>
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="grid min-w-0 content-start gap-6">
          {canStartRuns ? (
            <NewRunCard projectId={projectId} />
          ) : (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              {t("viewerNotice")}
            </p>
          )}
          <RunsCard projectId={projectId} />
        </div>
        <MembersCard projectId={projectId} canManage={canManageMembers} />
      </div>
    </>
  );
}

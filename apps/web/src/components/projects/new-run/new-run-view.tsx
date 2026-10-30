"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeftIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { getProjectOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { projectPermissions } from "../permissions";
import { projectHref } from "../project-tabs";
import { NewRunWizard } from "./new-run-wizard";

/** /projects/<id>/runs/new: the wizard, for the people who may start runs in the project. */
export function NewRunView({ projectId }: { projectId: string }) {
  const t = useTranslations("wizard");
  const user = useCurrentUser();
  const project = useQuery(getProjectOptions({ path: { project_id: projectId } }));

  const back = (
    <Link
      href={projectHref(projectId)}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ChevronLeftIcon className="size-4" aria-hidden />
      {t("backToProject")}
    </Link>
  );

  if (project.isPending) {
    return (
      <>
        {back}
        <LoadingRows rows={5} />
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

  const { canStartRuns } = projectPermissions(user, project.data.my_role);
  return (
    <>
      {back}
      <PageHeader
        title={t("title")}
        description={t("description", { project: project.data.name })}
      />
      {canStartRuns ? (
        <NewRunWizard projectId={projectId} allowFreeModels={project.data.allow_free_models} />
      ) : (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          {t("notAllowed")}
        </p>
      )}
    </>
  );
}

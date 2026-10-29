"use client";

import { useQuery } from "@tanstack/react-query";
import { FolderIcon, LockIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { EmptyState, LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BudgetCard } from "./budget-card";
import { CreateProjectDialog } from "./create-project-dialog";

export function Dashboard() {
  const t = useTranslations("dashboard");
  const format = useFormatter();
  const user = useCurrentUser();
  const projects = useQuery(listProjectsOptions());

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("welcome", { name: user.name || user.email })}
        actions={<CreateProjectDialog />}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section aria-labelledby="projects-heading" className="order-2 min-w-0 lg:order-1">
          <h2 id="projects-heading" className="mb-3 text-base font-semibold">
            {t("projects")}
          </h2>
          {projects.isPending ? (
            <LoadingRows rows={4} />
          ) : projects.isError ? (
            <QueryError error={projects.error} onRetry={() => projects.refetch()} />
          ) : projects.data.length === 0 ? (
            <EmptyState
              icon={<FolderIcon aria-hidden />}
              title={t("emptyTitle")}
              description={t("emptyDescription")}
            />
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {projects.data.map((project) => (
                <li key={project.id}>
                  <Link
                    href={`/projects/${project.id}`}
                    className="block h-full rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                  >
                    <Card className="h-full transition-colors hover:bg-muted/50">
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          <span className="truncate">{project.name}</span>
                          {project.privacy === "confidential" && (
                            <LockIcon
                              className="size-3.5 shrink-0 text-muted-foreground"
                              aria-label={t("confidential")}
                            />
                          )}
                        </CardTitle>
                        <CardDescription className="line-clamp-2 min-h-10">
                          {project.description || t("noDescription")}
                        </CardDescription>
                        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
                          <RoleBadge role={project.my_role} />
                          <span>
                            {t("createdAt", {
                              date: format.dateTime(new Date(project.created_at), {
                                dateStyle: "medium",
                              }),
                            })}
                          </span>
                        </div>
                      </CardHeader>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <aside className="order-1 lg:order-2">
          <BudgetCard />
        </aside>
      </div>
    </>
  );
}

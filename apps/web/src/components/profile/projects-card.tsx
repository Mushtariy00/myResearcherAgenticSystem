"use client";

import { FolderIcon, LockIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useMyProjects } from "./use-my-projects";

/** The projects I belong to and my role in each, linking to the project pages. */
export function ProjectsCard({ className }: { className?: string }) {
  const t = useTranslations();
  const { query, projects, otherCount } = useMyProjects();

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{t("profile.projects.title")}</CardTitle>
        <CardDescription>{t("profile.projects.description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {query.isPending ? (
          <LoadingRows rows={3} />
        ) : query.isError ? (
          <QueryError error={query.error} onRetry={() => query.refetch()} />
        ) : projects.length === 0 ? (
          <EmptyState icon={<FolderIcon aria-hidden />} title={t("profile.projects.empty")} />
        ) : (
          <ul className="grid gap-1 sm:grid-cols-2">
            {projects.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/projects/${encodeURIComponent(project.id)}`}
                  className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                    <span className="truncate">{project.name}</span>
                    {project.privacy === "confidential" && (
                      <LockIcon
                        className="size-3.5 shrink-0 text-muted-foreground"
                        aria-label={t("dashboard.confidential")}
                      />
                    )}
                  </span>
                  <RoleBadge role={project.my_role} />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {query.isSuccess && otherCount > 0 && (
          <p className="text-xs text-muted-foreground">
            {t("profile.projects.adminAccess", { count: otherCount })}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

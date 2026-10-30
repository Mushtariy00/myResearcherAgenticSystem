"use client";

import { Tabs } from "@base-ui/react/tabs";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpenTextIcon,
  ChevronLeftIcon,
  HistoryIcon,
  LockIcon,
  PlayIcon,
  SettingsIcon,
  UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { getProjectOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { PaperBrowser } from "@/components/papers/paper-browser";
import { buttonVariants } from "@/components/ui/button";
import { MembersPanel } from "./members-panel";
import { projectPermissions } from "./permissions";
import { PROJECT_TABS, type ProjectTab, projectTabOf, useProjectTab } from "./project-tabs";
import { RunsTable } from "./runs-table";
import { SettingsPanel } from "./settings-panel";

const TAB_ICONS = {
  runs: HistoryIcon,
  papers: BookOpenTextIcon,
  members: UsersIcon,
  settings: SettingsIcon,
} as const satisfies Record<ProjectTab, unknown>;

const PANEL_CLASS =
  "rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-offset-4 focus-visible:ring-offset-background";

/** A project: its runs, papers, members and settings, one tab each (the tab is in the URL). */
export function ProjectView({ projectId }: { projectId: string }) {
  const t = useTranslations("project");
  const user = useCurrentUser();
  const project = useQuery(getProjectOptions({ path: { project_id: projectId } }));
  const [tab, setTab] = useProjectTab();

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
  const { canStartRuns, canManage } = projectPermissions(user, role);
  const newRunHref = `/projects/${encodeURIComponent(projectId)}/runs/new`;

  return (
    <>
      {back}
      <PageHeader
        title={project.data.name}
        description={project.data.description || undefined}
        actions={
          canStartRuns ? (
            <Link href={newRunHref} className={buttonVariants()}>
              <PlayIcon aria-hidden />
              {t("newRun.title")}
            </Link>
          ) : undefined
        }
      >
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

      <Tabs.Root value={tab} onValueChange={(value) => setTab(projectTabOf(value))}>
        <Tabs.List
          aria-label={t("tabs.label")}
          className="mb-6 flex gap-1 overflow-x-auto border-b [scrollbar-width:none]"
        >
          {PROJECT_TABS.map((value) => {
            const Icon = TAB_ICONS[value];
            return (
              <Tabs.Tab
                key={value}
                value={value}
                className="-mb-px inline-flex h-9 shrink-0 items-center gap-1.5 rounded-t-md border-b-2 border-transparent px-3 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-active:border-primary data-active:text-foreground"
              >
                <Icon aria-hidden className="size-4" />
                {t(`tabs.${value}`)}
              </Tabs.Tab>
            );
          })}
        </Tabs.List>
        <Tabs.Panel value="runs" className={PANEL_CLASS}>
          <div className="grid gap-4">
            {!canStartRuns && (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                {t("viewerNotice")}
              </p>
            )}
            <RunsTable projectId={projectId} canStartRuns={canStartRuns} newRunHref={newRunHref} />
          </div>
        </Tabs.Panel>
        <Tabs.Panel value="papers" className={PANEL_CLASS}>
          <PaperBrowser projectId={projectId} />
        </Tabs.Panel>
        <Tabs.Panel value="members" className={PANEL_CLASS}>
          <MembersPanel projectId={projectId} canManage={canManage} />
        </Tabs.Panel>
        <Tabs.Panel value="settings" className={PANEL_CLASS}>
          <SettingsPanel projectId={projectId} canEdit={canManage} />
        </Tabs.Panel>
      </Tabs.Root>
    </>
  );
}

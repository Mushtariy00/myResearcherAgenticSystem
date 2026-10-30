"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  EyeIcon,
  FolderXIcon,
  HistoryIcon,
  LibraryIcon,
  LockIcon,
  PlusIcon,
  SettingsIcon,
  UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { getProjectOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { toApiError } from "@/lib/api-error";
import { cn } from "@/lib/utils";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import {
  AnimatedTabs,
  AnimatedTabsList,
  AnimatedTabsPanel,
  AnimatedTabsTab,
} from "@/studio/components/effects/animated-tabs";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { NewRunWizard } from "@/studio/components/wizard/new-run-wizard";
import { STUDIO_ROUTES } from "@/studio/lib/nav";
import { GHOST_BUTTON } from "@/studio/lib/ui";
import { ProjectMembersTab } from "./project-members-tab";
import { ProjectPapersTab } from "./project-papers-tab";
import { projectPermissions } from "./project-permissions";
import { ProjectRunsTab } from "./project-runs-tab";
import { ProjectSettingsTab } from "./project-settings-tab";

export const PROJECT_TABS = ["runs", "papers", "members", "settings"] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];

export function isProjectTab(value: unknown): value is ProjectTab {
  return typeof value === "string" && (PROJECT_TABS as readonly string[]).includes(value);
}

const TAB_ICONS = {
  runs: HistoryIcon,
  papers: LibraryIcon,
  members: UsersIcon,
  settings: SettingsIcon,
} as const;

const ROLE_TONES = { owner: "info", researcher: "success", viewer: "neutral" } as const;

/** Keeps the open tab in the address (`?tab=`), so it survives a reload and can be shared. */
function rememberTab(tab: ProjectTab): void {
  if (typeof window === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  if (tab === "runs") {
    url.searchParams.delete("tab");
  } else {
    url.searchParams.set("tab", tab);
  }
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

/**
 * A project in Studio: its name, role and privacy, the new-run wizard for people who may start
 * runs, and animated tabs for its runs, papers, members and settings, with the same features and
 * permissions as Classic. Each tab's data loads when the tab opens.
 */
export function StudioProjectView({
  projectId,
  initialTab,
}: {
  projectId: string;
  initialTab?: string;
}) {
  const t = useTranslations("studioWork.project");
  const tProject = useTranslations("project");
  const tRoles = useTranslations("roles");
  const user = useCurrentUser();
  const project = useQuery(getProjectOptions({ path: { project_id: projectId } }));
  const [tab, setTab] = useState<ProjectTab>(isProjectTab(initialTab) ? initialTab : "runs");
  const [wizardOpen, setWizardOpen] = useState(false);
  // The wizard (and its cost estimate request) mounts on first use, then stays mounted so its
  // values survive closing and opening it again.
  const [wizardUsed, setWizardUsed] = useState(false);

  function openWizard() {
    setWizardUsed(true);
    setWizardOpen(true);
  }

  const back = (
    <Link href={STUDIO_ROUTES.projects} className={cn(GHOST_BUTTON, "-ml-3 h-8 w-fit px-3")}>
      <ArrowLeftIcon aria-hidden />
      {tProject("back")}
    </Link>
  );

  if (project.isPending) {
    return (
      <div className="grid gap-6" aria-busy="true">
        <LoadingStatus label={t("loading")} />
        {back}
        <ShimmerSkeleton className="h-10 w-2/3 max-w-md" />
        <ShimmerSkeleton className="h-5 w-1/2 max-w-sm" />
        <ShimmerSkeleton className="h-10 w-full max-w-lg rounded-xl" />
        <ShimmerSkeleton className="h-64 rounded-2xl" />
      </div>
    );
  }
  if (project.isError) {
    const code = toApiError(project.error).code;
    if (code === "project.not_found" || code === "permission.denied") {
      return (
        <StudioStatePanel
          icon={<FolderXIcon aria-hidden />}
          title={t("notFoundTitle")}
          description={t("notFoundDescription")}
          action={{ href: STUDIO_ROUTES.projects, label: tProject("back") }}
        />
      );
    }
    return (
      <div className="grid gap-6">
        {back}
        <StudioInlineError error={project.error} onRetry={() => project.refetch()} />
      </div>
    );
  }

  const data = project.data;
  const permissions = projectPermissions(user.role, data.my_role);
  const role = data.my_role;

  function changeTab(next: string) {
    if (isProjectTab(next)) {
      setTab(next);
      rememberTab(next);
    }
  }

  return (
    <div className="grid min-w-0 gap-6 lg:gap-8">
      {back}
      <header className="studio-rise flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="grid min-w-0 gap-2">
          <h1 className="studio-display min-w-0 text-3xl text-foreground sm:text-4xl">
            {data.name}
          </h1>
          {data.description && (
            <p className="max-w-3xl text-base text-pretty text-muted-foreground">
              {data.description}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
            {role ? (
              <span
                data-tone={ROLE_TONES[role]}
                className="inline-flex h-6 items-center rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2.5 font-medium text-(--tone-fg)"
              >
                {t("yourRole", { role: tRoles(role) })}
              </span>
            ) : user.role === "admin" ? (
              <span
                data-tone="info"
                className="inline-flex h-6 items-center rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2.5 font-medium text-(--tone-fg)"
              >
                {t("adminAccess")}
              </span>
            ) : null}
            {data.privacy === "confidential" && (
              <span
                data-tone="warning"
                title={tProject("confidential")}
                className="inline-flex h-6 items-center gap-1.5 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2.5 font-medium text-(--tone-fg)"
              >
                <LockIcon aria-hidden className="size-3" />
                {t("confidential")}
              </span>
            )}
          </div>
          {data.privacy === "confidential" && (
            <p className="max-w-3xl text-xs text-pretty text-muted-foreground">
              {tProject("confidential")}
            </p>
          )}
        </div>
        {permissions.canStartRuns ? (
          <ShimmerButton size="lg" onClick={openWizard} className="w-full sm:w-fit">
            <PlusIcon aria-hidden />
            {tProject("newRun.title")}
          </ShimmerButton>
        ) : (
          <p
            data-tone="neutral"
            className="flex max-w-sm items-start gap-2 rounded-xl border border-dashed border-(--tone)/45 px-3 py-2 text-sm text-pretty text-muted-foreground"
          >
            <EyeIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
            {tProject("viewerNotice")}
          </p>
        )}
      </header>

      <AnimatedTabs value={tab} onValueChange={changeTab} className="grid min-w-0 gap-5">
        <AnimatedTabsList aria-label={t("tabs.label")} className="w-fit">
          {PROJECT_TABS.map((value) => {
            const Icon = TAB_ICONS[value];
            return (
              <AnimatedTabsTab key={value} value={value}>
                {/* Icons step aside on phones, so the four tabs fit a 360px screen. */}
                <Icon aria-hidden className="hidden sm:block" />
                {t(`tabs.${value}`)}
              </AnimatedTabsTab>
            );
          })}
        </AnimatedTabsList>
        <AnimatedTabsPanel value="runs">
          <ProjectRunsTab
            projectId={projectId}
            onNewRun={permissions.canStartRuns ? openWizard : undefined}
          />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="papers">
          <ProjectPapersTab projectId={projectId} />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="members">
          <ProjectMembersTab projectId={projectId} canManage={permissions.canManageMembers} />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="settings">
          <ProjectSettingsTab projectId={projectId} canEdit={permissions.canEditSettings} />
        </AnimatedTabsPanel>
      </AnimatedTabs>

      {permissions.canStartRuns && wizardUsed && (
        <NewRunWizard
          key={projectId}
          projectId={projectId}
          open={wizardOpen}
          onOpenChange={setWizardOpen}
          allowFreeModels={data.allow_free_models}
        />
      )}
    </div>
  );
}

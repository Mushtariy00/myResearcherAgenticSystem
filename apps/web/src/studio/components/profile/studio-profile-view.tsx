"use client";

import { ArrowUpRightIcon, FolderOpenIcon, LockIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCurrentUser } from "@/components/app/current-user";
import { QueryError } from "@/components/app/query-state";
import { useMyProjects } from "@/components/profile/use-my-projects";
import { PROFILE_USAGE_DAYS } from "@/components/profile/use-my-usage";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioAvatar } from "@/studio/components/shell/user-card";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { studioProjectPath } from "@/studio/lib/nav";
import { StudioPasswordForm } from "./studio-password-form";
import { StudioPreferences } from "./studio-preferences";
import { StudioSection, TonePill } from "./studio-section";
import { StudioUsage } from "./studio-usage";

const ROLE_TONES = { owner: "info", researcher: "success", viewer: "neutral" } as const;

function StudioProjects() {
  const t = useTranslations();
  const { query, projects, otherCount } = useMyProjects();

  if (query.isPending) {
    return (
      <div className="grid gap-2 sm:grid-cols-2" aria-busy="true">
        <LoadingStatus label={t("common.loading")} />
        {Array.from({ length: 4 }, (_, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
          <ShimmerSkeleton key={index} className="h-12 rounded-xl" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return <QueryError error={query.error} onRetry={() => query.refetch()} />;
  }
  return (
    <div className="grid gap-3">
      {projects.length === 0 ? (
        <StudioStatePanel
          variant="section"
          headingLevel={3}
          icon={<FolderOpenIcon aria-hidden />}
          title={t("profile.projects.empty")}
          description={t("dashboard.emptyDescription")}
        />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {projects.map((project) => (
            <li key={project.id} className="min-w-0">
              <Link
                href={studioProjectPath(project.id)}
                className="group/project flex items-center justify-between gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2.5 outline-none transition-colors hover:bg-(--studio-hover) focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-foreground">
                  <span className="truncate">{project.name}</span>
                  {project.privacy === "confidential" && (
                    <LockIcon
                      className="size-3.5 shrink-0 text-muted-foreground"
                      aria-label={t("dashboard.confidential")}
                    />
                  )}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <TonePill tone={ROLE_TONES[project.my_role]}>
                    {t(`roles.${project.my_role}`)}
                  </TonePill>
                  <ArrowUpRightIcon
                    aria-hidden
                    className="size-4 text-muted-foreground transition-transform duration-200 group-hover/project:translate-x-0.5 group-hover/project:-translate-y-0.5 motion-reduce:transition-none"
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {otherCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {t("profile.projects.adminAccess", { count: otherCount })}
        </p>
      )}
    </div>
  );
}

/**
 * The Studio profile page: who I am, language and theme, my password, my budget and LLM use,
 * and my projects with my role in each; the same data and actions as the Classic page.
 */
export function StudioProfileView() {
  const t = useTranslations();
  const user = useCurrentUser();

  return (
    <div className="grid gap-8">
      <header className="studio-rise flex flex-wrap items-center gap-4">
        <StudioAvatar name={user.name} email={user.email} className="size-14 text-base" />
        <div className="grid min-w-0 gap-1">
          <h1 className="studio-display text-3xl text-foreground sm:text-4xl">
            {t("profile.title")}
          </h1>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">
              {user.name || t("profile.account.noName")}
            </span>
            <span aria-hidden>·</span>
            <span className="break-all">{user.email}</span>
            <TonePill tone={user.role === "admin" ? "info" : "neutral"}>
              {t(`roles.${user.role}`)}
            </TonePill>
          </p>
        </div>
      </header>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="grid content-start gap-6">
          <StudioSection
            id="studio-profile-usage"
            title={t("profile.usage.title")}
            description={t("profile.usage.description", { days: PROFILE_USAGE_DAYS })}
          >
            <StudioUsage />
          </StudioSection>
          <StudioSection
            id="studio-profile-projects"
            title={t("profile.projects.title")}
            description={t("profile.projects.description")}
          >
            <StudioProjects />
          </StudioSection>
        </div>
        <div className="grid content-start gap-6">
          <StudioSection
            id="studio-profile-preferences"
            title={t("profile.preferences.title")}
            description={t("profile.preferences.description")}
          >
            <StudioPreferences />
          </StudioSection>
          <StudioSection
            id="studio-profile-password"
            title={t("profile.password.title")}
            description={t("profile.password.description")}
          >
            <StudioPasswordForm />
          </StudioSection>
        </div>
      </div>
    </div>
  );
}

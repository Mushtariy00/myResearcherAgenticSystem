"use client";

import { ArrowUpRightIcon, LockIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import type { ProjectOut } from "@/client";
import { cn } from "@/lib/utils";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { SpotlightCard } from "@/studio/components/effects/spotlight-card";
import { riseDelay } from "@/studio/lib/motion";
import { studioProjectPath } from "@/studio/lib/nav";

const ROLE_TONES = { owner: "info", researcher: "success", viewer: "neutral" } as const;

/**
 * A project as a glass card with a cursor spotlight, linking to its Studio page. `activeRuns`
 * (from the dashboard's recent runs) adds a live count of runs still in progress.
 */
export function ProjectCard({
  project,
  index = 0,
  activeRuns = 0,
}: {
  project: ProjectOut;
  index?: number;
  activeRuns?: number;
}) {
  const t = useTranslations();
  const format = useFormatter();
  const role = project.my_role;

  return (
    <SpotlightCard
      render={<Link href={studioProjectPath(project.id)} />}
      className={cn("studio-rise group/project flex h-full flex-col gap-4 p-5")}
      style={{ "--rise-delay": riseDelay(index) } as CSSProperties}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="flex min-w-0 items-center gap-2 text-base font-semibold tracking-tight text-foreground">
          <span className="truncate">{project.name}</span>
          {project.privacy === "confidential" && (
            <LockIcon
              className="size-3.5 shrink-0 text-muted-foreground"
              aria-label={t("dashboard.confidential")}
            />
          )}
        </h3>
        <ArrowUpRightIcon
          aria-hidden
          className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-hover/project:translate-x-0.5 group-hover/project:-translate-y-0.5 group-hover/project:text-foreground motion-reduce:transition-none"
        />
      </div>
      <p className="line-clamp-2 min-h-10 text-sm text-pretty text-muted-foreground">
        {project.description || t("dashboard.noDescription")}
      </p>
      <div className="mt-auto flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {role && (
          <span
            data-tone={ROLE_TONES[role]}
            className="inline-flex h-5 items-center rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 font-medium text-(--tone-fg)"
          >
            {t(`roles.${role}`)}
          </span>
        )}
        {activeRuns > 0 && (
          <span
            data-tone="info"
            className="inline-flex h-5 items-center gap-1.5 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 font-medium text-(--tone-fg)"
          >
            <PulseDot tone="info" live size="sm" />
            {t("studioWork.dashboard.projects.active", { count: activeRuns })}
          </span>
        )}
        <span>
          {t("dashboard.createdAt", {
            date: format.dateTime(new Date(project.created_at), { dateStyle: "medium" }),
          })}
        </span>
      </div>
    </SpotlightCard>
  );
}

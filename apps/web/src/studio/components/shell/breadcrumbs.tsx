"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRightIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { cn } from "@/lib/utils";
import { type Crumb, studioBreadcrumbs } from "@/studio/lib/nav";
import { useNavLabels } from "./studio-nav-list";

/**
 * Where the current page sits: Dashboard › Projects › <project name>. On phones only the current
 * page is shown. Project names come from the projects list (already cached by the dashboard).
 */
export function StudioBreadcrumbs({ className }: { className?: string }) {
  const t = useTranslations("studio.shell");
  const pathname = usePathname();
  const navLabels = useNavLabels();
  const crumbs = studioBreadcrumbs(pathname);
  const needsProjects = crumbs.some((crumb) => crumb.label.kind === "project");
  const projects = useQuery({ ...listProjectsOptions(), enabled: needsProjects });

  function labelOf(crumb: Crumb): string {
    const { label } = crumb;
    switch (label.kind) {
      case "nav":
        return navLabels[label.id];
      case "project":
        return (
          projects.data?.find((project) => project.id === label.id)?.name ?? t("crumbs.project")
        );
      case "run":
        return t("crumbs.run");
      case "paper":
        return t("crumbs.paper");
      case "profile":
        return t("crumbs.profile");
      case "text":
        return label.text;
    }
  }

  return (
    <nav aria-label={t("breadcrumb")} className={cn("min-w-0", className)}>
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          const label = labelOf(crumb);
          return (
            <li
              key={crumb.key}
              className={cn("flex min-w-0 items-center gap-1.5", !last && "hidden sm:flex")}
            >
              {crumb.href && !last ? (
                <Link
                  href={crumb.href}
                  className="truncate rounded-md text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {label}
                </Link>
              ) : (
                <span
                  aria-current={last ? "page" : undefined}
                  className={cn(
                    "truncate",
                    last ? "font-medium text-foreground" : "text-muted-foreground",
                  )}
                >
                  {label}
                </span>
              )}
              {!last && (
                <ChevronRightIcon aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

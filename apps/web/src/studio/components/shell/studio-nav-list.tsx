"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import { LayoutGroup, motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCurrentUser } from "@/components/app/current-user";
import { cn } from "@/lib/utils";
import { useUnreadNotifications } from "@/studio/hooks/use-unread-notifications";
import { SPRING } from "@/studio/lib/motion";
import { activeNavId, type StudioNavId, visibleNav } from "@/studio/lib/nav";

/** Translated sidebar labels (shared labels come from the existing namespaces). */
export function useNavLabels(): Record<StudioNavId, string> {
  const t = useTranslations();
  return {
    dashboard: t("nav.dashboard"),
    projects: t("studio.shell.nav.projects"),
    papers: t("studio.shell.nav.papers"),
    notifications: t("common.notifications"),
    admin: t("nav.admin"),
  };
}

/**
 * The Studio navigation: Dashboard, Projects, Papers, Notifications (unread count) and Admin
 * (lab admins only). The active item carries `aria-current="page"` and a highlight that slides
 * between items (shared `layoutId`, scoped by `layoutGroup` so the sidebar and the mobile sheet
 * never animate into each other). In the collapsed sidebar the labels stay for screen readers
 * and show as tooltips on hover and focus; collapsed styling comes from CSS on `#studio-shell`,
 * so it is right from the first paint.
 */
export function StudioNavList({
  collapsed = false,
  layoutGroup,
  onNavigate,
}: {
  collapsed?: boolean;
  layoutGroup: string;
  onNavigate?: () => void;
}) {
  const t = useTranslations();
  const pathname = usePathname();
  const user = useCurrentUser();
  const labels = useNavLabels();
  const unread = useUnreadNotifications().count;
  const active = activeNavId(pathname);

  return (
    <nav aria-label={t("nav.main")}>
      <LayoutGroup id={layoutGroup}>
        <Tooltip.Provider delay={250}>
          <ul className="relative isolate grid gap-0.5">
            {visibleNav(user.role).map((item) => {
              const isActive = item.id === active;
              const Icon = item.icon;
              const label = labels[item.id];
              const count = item.id === "notifications" && unread ? unread : 0;
              return (
                <li key={item.id}>
                  <Tooltip.Root disabled={!collapsed}>
                    <Tooltip.Trigger
                      render={
                        <Link
                          href={item.href}
                          aria-current={isActive ? "page" : undefined}
                          onClick={onNavigate}
                          className={cn(
                            "relative flex h-9 items-center gap-3 rounded-[10px] px-2.5 text-sm font-medium outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50",
                            "group-data-[sidebar=collapsed]/shell:justify-center group-data-[sidebar=collapsed]/shell:px-0",
                            isActive
                              ? "text-foreground"
                              : "text-muted-foreground hover:bg-(--studio-hover) hover:text-foreground",
                          )}
                        />
                      }
                    >
                      {isActive && (
                        <motion.span
                          layoutId="studio-nav-active"
                          transition={SPRING}
                          aria-hidden
                          className="absolute inset-0 z-0 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass-strong) shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)]"
                        />
                      )}
                      <Icon
                        aria-hidden
                        className={cn(
                          "relative z-10 size-4.5 shrink-0",
                          isActive && "text-(--studio-accent-fg)",
                        )}
                      />
                      <span className="studio-sidebar-label relative z-10 truncate group-data-[sidebar=collapsed]/shell:sr-only">
                        {label}
                      </span>
                      {count > 0 && (
                        <>
                          <span
                            aria-hidden
                            className="relative z-10 ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[0.7rem] font-semibold text-primary-foreground tabular-nums group-data-[sidebar=collapsed]/shell:absolute group-data-[sidebar=collapsed]/shell:top-1 group-data-[sidebar=collapsed]/shell:right-1 group-data-[sidebar=collapsed]/shell:h-2 group-data-[sidebar=collapsed]/shell:min-w-2 group-data-[sidebar=collapsed]/shell:p-0 group-data-[sidebar=collapsed]/shell:text-[0px]"
                          >
                            {count > 99 ? "99+" : count}
                          </span>
                          <span className="sr-only">{t("studio.shell.unread", { count })}</span>
                        </>
                      )}
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Positioner side="right" sideOffset={12}>
                        <Tooltip.Popup className="origin-(--transform-origin) rounded-lg border border-(--studio-glass-border) bg-popover px-2.5 py-1.5 text-xs font-medium text-popover-foreground shadow-lg transition-[scale,opacity] duration-150 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0 motion-reduce:transition-none">
                          {label}
                        </Tooltip.Popup>
                      </Tooltip.Positioner>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                </li>
              );
            })}
          </ul>
        </Tooltip.Provider>
      </LayoutGroup>
    </nav>
  );
}

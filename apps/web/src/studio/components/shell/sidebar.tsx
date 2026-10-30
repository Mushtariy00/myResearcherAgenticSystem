"use client";

import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { StudioBrand } from "@/studio/components/studio-brand";
import { STUDIO_ROUTES } from "@/studio/lib/nav";
import { GHOST_BUTTON } from "@/studio/lib/ui";
import { StudioNavList } from "./studio-nav-list";
import { StudioUserCard } from "./user-card";

/**
 * The desktop sidebar (lg and up): glass, full height, collapsible to icons. Its width and the
 * collapsed look come from `data-sidebar` on `#studio-shell`, so a remembered collapsed state
 * is already right on the first paint. It does not blur: content never scrolls beneath it.
 * The width switches at once (animating it would reflow the page on every frame); after a
 * toggle the labels fade back in instead (`.studio-sidebar-label`, globals.css).
 */
export function StudioSidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const t = useTranslations("studio.shell");
  const toggleLabel = collapsed ? t("expand") : t("collapse");

  return (
    <div
      id="studio-sidebar"
      className="sticky top-0 z-20 hidden h-dvh w-64 shrink-0 flex-col border-r border-(--studio-glass-border) bg-(--studio-glass) px-3 py-3 shadow-[inset_-1px_0_0_0_var(--studio-glass-highlight)] lg:flex group-data-[sidebar=collapsed]/shell:w-19"
    >
      <div className="flex h-11 items-center px-1.5 group-data-[sidebar=collapsed]/shell:justify-center group-data-[sidebar=collapsed]/shell:px-0">
        <StudioBrand href={STUDIO_ROUTES.dashboard} collapsible />
      </div>
      {/* Reaches 4px past the items: the scroll box clips, and focus rings must stay whole. */}
      <div className="-mx-1 mt-4 min-h-0 flex-1 overflow-x-hidden overflow-y-auto p-1">
        <StudioNavList collapsed={collapsed} layoutGroup="studio-nav-sidebar" />
      </div>
      <div className="grid gap-1 border-t border-(--studio-glass-border) pt-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-controls="studio-sidebar"
          title={toggleLabel}
          className={cn(
            GHOST_BUTTON,
            "w-full justify-start px-2.5 group-data-[sidebar=collapsed]/shell:justify-center group-data-[sidebar=collapsed]/shell:px-0",
          )}
        >
          <PanelLeftCloseIcon aria-hidden className="group-data-[sidebar=collapsed]/shell:hidden" />
          <PanelLeftOpenIcon
            aria-hidden
            className="hidden group-data-[sidebar=collapsed]/shell:block"
          />
          <span className="studio-sidebar-label truncate group-data-[sidebar=collapsed]/shell:sr-only">
            {toggleLabel}
          </span>
        </button>
        <StudioUserCard collapsed={collapsed} />
      </div>
    </div>
  );
}

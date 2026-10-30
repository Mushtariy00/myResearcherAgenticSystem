"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";
import { InlineScript } from "@/studio/components/inline-script";
import { SIDEBAR_SCRIPT, useSidebarCollapsed } from "@/studio/hooks/use-sidebar-state";
import { CommandPalette } from "./command-palette";
import { StudioMobileNav } from "./mobile-nav";
import { StudioSidebar } from "./sidebar";
import { StudioTopBar } from "./top-bar";

/**
 * The signed-in Studio frame: skip link, glass sidebar (a sheet on phones), sticky top bar,
 * the ⌘K palette, and the page content (at most 1400px wide). Rendered by the (app) layout
 * inside CurrentUserProvider.
 */
export function StudioShell({ children }: { children: ReactNode }) {
  const t = useTranslations("nav");
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  /* Set by the first toggle here, so the sidebar labels fade in on expand but not on load. */
  const [sidebarToggled, setSidebarToggled] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  function toggleSidebar() {
    setSidebarToggled(true);
    setCollapsed(!collapsed);
  }

  return (
    <div
      id="studio-shell"
      data-sidebar={collapsed ? "collapsed" : "expanded"}
      data-sidebar-motion={sidebarToggled ? "" : undefined}
      suppressHydrationWarning
      className="group/shell relative flex min-h-dvh"
    >
      <InlineScript html={SIDEBAR_SCRIPT} />
      <a
        href="#studio-main"
        className="sr-only rounded-[10px] bg-popover px-3 py-2 text-sm font-medium text-popover-foreground shadow-lg focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:outline-none focus:ring-3 focus:ring-ring/60"
      >
        {t("skipToContent")}
      </a>
      <StudioSidebar collapsed={collapsed} onToggle={toggleSidebar} />
      <div className="flex min-w-0 flex-1 flex-col">
        <StudioTopBar
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenMenu={() => setMenuOpen(true)}
        />
        <main
          id="studio-main"
          tabIndex={-1}
          className="mx-auto w-full max-w-350 flex-1 px-4 py-6 outline-none sm:px-6 sm:py-8 lg:px-10 lg:py-10"
        >
          {children}
        </main>
      </div>
      <StudioMobileNav open={menuOpen} onOpenChange={setMenuOpen} />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}

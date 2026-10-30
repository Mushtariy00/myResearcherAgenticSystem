"use client";

import { MenuIcon, SearchIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { LocaleSwitcher } from "@/components/app/locale-switcher";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { VersionSwitch } from "@/components/app/version-switch";
import { cn } from "@/lib/utils";
import { ICON_BUTTON, SHARED_CONTROL } from "@/studio/lib/ui";
import { StudioBreadcrumbs } from "./breadcrumbs";
import { NotificationsBell } from "./notifications-bell";
import { ShortcutHint } from "./shortcut-hint";

const SHORTCUT = "Meta+K Control+K";

/**
 * The sticky top bar (the one blurred layer of the shell): breadcrumbs, search (⌘K), the
 * notifications bell, the switch to Classic, language and theme. On phones the menu button
 * opens the navigation sheet, and less-used controls step back.
 */
export function StudioTopBar({
  onOpenPalette,
  onOpenMenu,
}: {
  onOpenPalette: () => void;
  onOpenMenu: () => void;
}) {
  const t = useTranslations("studio.shell");

  return (
    <header className="studio-blur sticky top-0 z-30 border-b border-(--studio-glass-border) bg-(--studio-topbar)">
      <div className="mx-auto flex h-14 w-full max-w-350 items-center gap-2 px-4 sm:px-6 lg:px-10">
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label={t("openMenu")}
          aria-haspopup="dialog"
          className={cn(ICON_BUTTON, "-ml-1.5 lg:hidden")}
        >
          <MenuIcon aria-hidden />
        </button>
        <StudioBreadcrumbs className="flex-1" />
        <div className="flex shrink-0 items-center gap-0.5 sm:gap-1">
          <button
            type="button"
            onClick={onOpenPalette}
            aria-keyshortcuts={SHORTCUT}
            aria-haspopup="dialog"
            className="hidden h-9 w-60 items-center gap-2 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-3 text-sm text-muted-foreground shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)] outline-none transition-colors hover:bg-(--studio-hover) hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 md:inline-flex"
          >
            <SearchIcon aria-hidden className="size-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate text-left">{t("searchPlaceholder")}</span>
            <ShortcutHint />
          </button>
          <button
            type="button"
            onClick={onOpenPalette}
            aria-label={t("search")}
            aria-keyshortcuts={SHORTCUT}
            aria-haspopup="dialog"
            className={cn(ICON_BUTTON, "md:hidden")}
          >
            <SearchIcon aria-hidden />
          </button>
          <NotificationsBell />
          <VersionSwitch className="hidden h-9 rounded-[10px] px-2.5 text-muted-foreground hover:bg-(--studio-hover) sm:inline-flex" />
          <div className={SHARED_CONTROL}>
            <LocaleSwitcher />
          </div>
          <div className={SHARED_CONTROL}>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>
  );
}

"use client";

import { FlaskConicalIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { NotificationsBell } from "@/components/notifications/notifications-bell";
import { cn } from "@/lib/utils";
import { useCurrentUser } from "./current-user";
import { LocaleSwitcher } from "./locale-switcher";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";
import { VersionSwitch } from "./version-switch";

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  const pathname = usePathname();
  const active =
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "shrink-0 rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        active && "bg-muted text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

/**
 * The Classic header: the app name, the main navigation (Dashboard, Papers, and Admin for lab
 * admins), the version, language and theme switches, the notifications bell and the account
 * menu. Below `md` the navigation moves to a second row, so nothing overflows on a phone.
 */
export function AppHeader() {
  const t = useTranslations();
  const user = useCurrentUser();

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-backdrop-filter:bg-background/70">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-3 px-4 md:h-14 md:flex-nowrap">
        <Link
          href="/"
          className="flex h-14 items-center gap-2 rounded-md font-semibold focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none md:h-auto"
        >
          <FlaskConicalIcon className="size-5 text-primary" aria-hidden />
          <span className="hidden lg:inline">{t("common.appName")}</span>
          <span className="lg:hidden">{t("common.appShortName")}</span>
        </Link>
        <nav
          aria-label={t("nav.main")}
          className="order-last -mx-1 flex basis-full items-center gap-1 overflow-x-auto pb-2 md:order-none md:mx-0 md:basis-auto md:pb-0"
        >
          <NavLink href="/">{t("nav.dashboard")}</NavLink>
          <NavLink href="/papers">{t("nav.papers")}</NavLink>
          {user.role === "admin" && <NavLink href="/admin">{t("nav.admin")}</NavLink>}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <VersionSwitch />
          <LocaleSwitcher />
          <ThemeToggle />
          <NotificationsBell />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

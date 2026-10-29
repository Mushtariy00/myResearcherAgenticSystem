"use client";

import { FlaskConicalIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useCurrentUser } from "./current-user";
import { LocaleSwitcher } from "./locale-switcher";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        active && "bg-muted text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

export function AppHeader() {
  const t = useTranslations();
  const user = useCurrentUser();

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-backdrop-filter:bg-background/70">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-3 px-4">
        <Link
          href="/"
          className="flex items-center gap-2 rounded-md font-semibold focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <FlaskConicalIcon className="size-5 text-primary" aria-hidden />
          <span className="hidden sm:inline">{t("common.appName")}</span>
          <span className="sm:hidden">{t("common.appShortName")}</span>
        </Link>
        <nav aria-label={t("nav.main")} className="flex items-center gap-1">
          <NavLink href="/">{t("nav.dashboard")}</NavLink>
          {user.role === "admin" && <NavLink href="/admin">{t("nav.admin")}</NavLink>}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <LocaleSwitcher />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

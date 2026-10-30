"use client";

import { BellIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { useUnreadNotifications } from "@/studio/hooks/use-unread-notifications";
import { STUDIO_ROUTES } from "@/studio/lib/nav";
import { ICON_BUTTON } from "@/studio/lib/ui";

/** The top bar bell: opens the notifications page; the badge shows the unread count. */
export function NotificationsBell({ className }: { className?: string }) {
  const t = useTranslations();
  const unread = useUnreadNotifications().count;
  const label = unread
    ? t("studio.shell.notificationsWithCount", { count: unread })
    : t("common.notifications");

  return (
    <Link
      href={STUDIO_ROUTES.notifications}
      aria-label={label}
      title={label}
      className={cn(ICON_BUTTON, className)}
    >
      <BellIcon aria-hidden />
      {unread ? (
        <span
          aria-hidden
          className="absolute top-1 right-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[0.625rem] leading-none font-semibold text-primary-foreground tabular-nums ring-2 ring-background animate-in zoom-in-50 duration-200"
        >
          {unread > 99 ? "99+" : unread}
        </span>
      ) : null}
    </Link>
  );
}

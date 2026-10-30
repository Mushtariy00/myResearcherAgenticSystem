"use client";

import { Popover } from "@base-ui/react/popover";
import { BellIcon, CheckCheckIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { Button, buttonVariants } from "@/components/ui/button";
import { useNotifications } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { BELL_LIMIT, badgeCount, NOTIFICATIONS_PATH } from "./notification-meta";
import { NotificationRow } from "./notification-row";
import { useNotificationActions, useNotificationItems } from "./use-notification-items";

/**
 * The Classic header bell: the unread count, and a popover with the latest notifications to
 * open (which marks them read) or mark read, plus a link to the notifications page.
 */
export function NotificationsBell() {
  const t = useTranslations("notifications");
  const notifications = useNotifications();
  const { query, items, unreadCount, isMarking } = notifications;
  const { markOne, markAll } = useNotificationActions(notifications);
  const toItem = useNotificationItems("");
  const [open, setOpen] = useState(false);
  const unread = unreadCount ?? 0;
  const label = unread > 0 ? t("bell.labelWithCount", { count: unread }) : t("bell.label");
  const latest = items.slice(0, BELL_LIMIT).map(toItem);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={label}
            title={label}
            className="relative"
          />
        }
      >
        <BellIcon aria-hidden />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute -top-1 -right-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[0.625rem] leading-none font-semibold text-primary-foreground tabular-nums ring-2 ring-background"
          >
            {badgeCount(unread)}
          </span>
        )}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="end" sideOffset={8} className="isolate z-50">
          <Popover.Popup className="flex max-h-[min(34rem,calc(100dvh-5rem))] w-[min(24rem,calc(100vw-2rem))] origin-(--transform-origin) flex-col overflow-hidden rounded-xl bg-popover text-popover-foreground shadow-lg ring-1 ring-foreground/10 outline-none transition-[transform,opacity] duration-150 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0 motion-reduce:transition-none">
            <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
              <Popover.Title className="text-sm font-semibold">{t("title")}</Popover.Title>
              <Button
                variant="ghost"
                size="xs"
                disabled={unread === 0 || isMarking}
                onClick={() => void markAll()}
              >
                <CheckCheckIcon aria-hidden />
                {t("markAllRead")}
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
              {query.isPending ? (
                <div className="p-1.5">
                  <LoadingRows rows={3} />
                </div>
              ) : query.isError ? (
                <div className="p-1.5">
                  <QueryError error={query.error} onRetry={() => query.refetch()} />
                </div>
              ) : latest.length === 0 ? (
                <div className="grid gap-1 px-3 py-8 text-center">
                  <p className="text-sm font-medium">{t("empty")}</p>
                  <p className="text-xs text-muted-foreground">{t("emptyDescription")}</p>
                </div>
              ) : (
                <ul aria-label={t("bell.latest")} className="grid gap-0.5">
                  {latest.map((item) => (
                    <li key={item.key}>
                      <NotificationRow
                        item={item}
                        onMarkRead={() => void markOne(item.key)}
                        onOpen={() => {
                          setOpen(false);
                          if (!item.read) {
                            void markOne(item.key);
                          }
                        }}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="border-t p-1.5">
              <Link
                href={NOTIFICATIONS_PATH.classic}
                onClick={() => setOpen(false)}
                className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "w-full")}
              >
                {t("bell.viewAll")}
              </Link>
            </div>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

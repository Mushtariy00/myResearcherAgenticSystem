"use client";

import { Popover } from "@base-ui/react/popover";
import { useQueryClient } from "@tanstack/react-query";
import { BellIcon, CheckCheckIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { QueryError } from "@/components/app/query-state";
import {
  BELL_LIMIT,
  badgeCount,
  NOTIFICATIONS_PATH,
} from "@/components/notifications/notification-meta";
import {
  useNotificationActions,
  useNotificationItems,
} from "@/components/notifications/use-notification-items";
import { useNotifications } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { AnimatedList } from "@/studio/components/effects/animated-list";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioNotificationRow } from "@/studio/components/notifications/studio-notification-row";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import { unreadNotificationsQueryKey } from "@/studio/hooks/use-unread-notifications";
import { glassClassName } from "@/studio/lib/glass";
import { GHOST_BUTTON, ICON_BUTTON } from "@/studio/lib/ui";

/**
 * The top bar bell: the unread count (useNotifications) as a badge that pops in when it
 * changes (a plain fade with reduced motion), and a popover with the latest notifications to
 * open or mark read, plus a link to the notifications page.
 */
export function NotificationsBell({ className }: { className?: string }) {
  const t = useTranslations("notifications");
  const notifications = useNotifications();
  const { query, items, unreadCount, isMarking } = notifications;
  const { markOne, markAll } = useNotificationActions(notifications);
  const toItem = useNotificationItems("/studio");
  const reduced = useReducedMotionPreference();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const unread = unreadCount ?? 0;
  const display = badgeCount(unread);
  const label = unread > 0 ? t("bell.labelWithCount", { count: unread }) : t("bell.label");
  const latest = items.slice(0, BELL_LIMIT).map(toItem);

  // The sidebar and the dashboard still read their own unread-count query; the bell is on
  // every Studio page, so it keeps that count in step with this one.
  useEffect(() => {
    if (unreadCount !== null) {
      queryClient.setQueryData(unreadNotificationsQueryKey, unreadCount);
    }
  }, [queryClient, unreadCount]);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger aria-label={label} title={label} className={cn(ICON_BUTTON, className)}>
        <BellIcon aria-hidden />
        {unread > 0 && (
          <span
            // A new key on every change replays the entrance.
            key={display}
            aria-hidden
            data-slot="unread-badge"
            className={cn(
              "absolute top-1 right-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[0.625rem] leading-none font-semibold text-primary-foreground tabular-nums ring-2 ring-background",
              "animate-in duration-200 fade-in-0 motion-reduce:[--tw-enter-scale:1]",
              !reduced && "zoom-in-50",
            )}
          >
            {display}
          </span>
        )}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="end" sideOffset={8} className="isolate z-50">
          <Popover.Popup
            className={cn(
              glassClassName({ variant: "solid" }),
              "flex max-h-[min(34rem,calc(100dvh-5rem))] w-[min(25rem,calc(100vw-2rem))] origin-(--transform-origin) flex-col overflow-hidden shadow-xl outline-none",
              "transition-[transform,opacity] duration-200 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0",
              "motion-reduce:data-ending-style:scale-100 motion-reduce:data-starting-style:scale-100",
            )}
          >
            <div className="flex items-center justify-between gap-2 border-b border-(--studio-glass-border) px-4 py-3">
              <Popover.Title className="text-sm font-semibold text-foreground">
                {t("title")}
              </Popover.Title>
              <button
                type="button"
                disabled={unread === 0 || isMarking}
                onClick={() => void markAll()}
                className={cn(
                  GHOST_BUTTON,
                  "h-8 px-2.5 text-xs disabled:pointer-events-none disabled:opacity-50",
                )}
              >
                <CheckCheckIcon aria-hidden />
                {t("markAllRead")}
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-1.5" aria-busy={query.isPending}>
              {query.isPending ? (
                <div className="grid gap-2 p-1.5">
                  <LoadingStatus label={t("loading")} />
                  {Array.from({ length: 3 }, (_, index) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
                    <ShimmerSkeleton key={index} className="h-14 rounded-xl" />
                  ))}
                </div>
              ) : query.isError ? (
                <div className="p-1.5">
                  <QueryError error={query.error} onRetry={() => query.refetch()} />
                </div>
              ) : latest.length === 0 ? (
                <div className="grid gap-1 px-4 py-10 text-center">
                  <p className="text-sm font-medium text-foreground">{t("empty")}</p>
                  <p className="text-xs text-muted-foreground">{t("emptyDescription")}</p>
                </div>
              ) : (
                <AnimatedList
                  items={latest}
                  getKey={(item) => item.key}
                  aria-label={t("bell.latest")}
                  className="gap-0.5"
                  renderItem={(item) => (
                    <StudioNotificationRow
                      item={item}
                      onMarkRead={() => void markOne(item.key)}
                      onOpen={() => {
                        setOpen(false);
                        if (!item.read) {
                          void markOne(item.key);
                        }
                      }}
                    />
                  )}
                />
              )}
            </div>
            <div className="border-t border-(--studio-glass-border) p-1.5">
              <Link
                href={NOTIFICATIONS_PATH.studio}
                onClick={() => setOpen(false)}
                className={cn(GHOST_BUTTON, "w-full")}
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

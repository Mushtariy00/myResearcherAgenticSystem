"use client";

import { BellOffIcon, CheckCheckIcon, InboxIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { QueryError } from "@/components/app/query-state";
import {
  NOTIFICATION_FILTERS,
  type NotificationFilter,
  olderUnread,
} from "@/components/notifications/notification-meta";
import {
  useNotificationActions,
  useNotificationItems,
} from "@/components/notifications/use-notification-items";
import { useNotifications } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { AnimatedList } from "@/studio/components/effects/animated-list";
import {
  AnimatedTabs,
  AnimatedTabsList,
  AnimatedTabsPanel,
  AnimatedTabsTab,
} from "@/studio/components/effects/animated-tabs";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";
import { StudioNotificationRow } from "./studio-notification-row";

/**
 * The Studio notifications page: the newest 50 notifications, or only the unread ones, in a
 * glass list whose items slide in and out; mark one or all of them read.
 */
export function StudioNotificationsView() {
  const t = useTranslations("notifications");
  const notifications = useNotifications();
  const { query, items, unreadCount, isMarking } = notifications;
  const { markOne, markAll } = useNotificationActions(notifications);
  const toItem = useNotificationItems("/studio");
  const [filter, setFilter] = useState<NotificationFilter>("all");
  const listedUnread = items.filter((item) => !item.read).length;
  const hidden = olderUnread(unreadCount, listedUnread);
  const shown = (filter === "unread" ? items.filter((item) => !item.read) : items).map(toItem);

  return (
    <div className="grid gap-8">
      <header className="studio-rise flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="grid gap-2">
          <h1 className="studio-display text-3xl text-foreground sm:text-4xl">{t("title")}</h1>
          <p className="text-base text-muted-foreground">{t("description")}</p>
        </div>
        <button
          type="button"
          disabled={!unreadCount || isMarking}
          onClick={() => void markAll()}
          className={cn(OUTLINE_BUTTON, "disabled:pointer-events-none disabled:opacity-50")}
        >
          <CheckCheckIcon aria-hidden />
          {t("markAllRead")}
        </button>
      </header>

      <AnimatedTabs
        value={filter}
        onValueChange={(value) => setFilter(value === "unread" ? "unread" : "all")}
        className="grid gap-4"
      >
        <AnimatedTabsList aria-label={t("filter.label")} className="w-fit">
          {NOTIFICATION_FILTERS.map((value) => (
            <AnimatedTabsTab key={value} value={value}>
              {value === "unread" && unreadCount
                ? t("filter.unreadCount", { count: unreadCount })
                : t(`filter.${value}`)}
            </AnimatedTabsTab>
          ))}
        </AnimatedTabsList>
        {NOTIFICATION_FILTERS.map((value) => (
          <AnimatedTabsPanel key={value} value={value} className="rounded-2xl">
            {query.isPending ? (
              <GlassCard className="grid gap-2 p-3" aria-busy="true">
                <LoadingStatus label={t("loading")} />
                {Array.from({ length: 5 }, (_, index) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
                  <ShimmerSkeleton key={index} className="h-16 rounded-xl" />
                ))}
              </GlassCard>
            ) : query.isError ? (
              <QueryError error={query.error} onRetry={() => query.refetch()} />
            ) : shown.length === 0 ? (
              <StudioStatePanel
                variant="section"
                headingLevel={2}
                icon={value === "unread" ? <BellOffIcon aria-hidden /> : <InboxIcon aria-hidden />}
                title={value === "unread" ? t("emptyUnread") : t("empty")}
                description={
                  value === "unread"
                    ? hidden > 0
                      ? t("olderUnread", { count: hidden })
                      : t("emptyUnreadDescription")
                    : t("emptyDescription")
                }
              />
            ) : (
              <GlassCard className="grid gap-2 p-1.5 sm:p-2">
                <AnimatedList
                  items={shown}
                  getKey={(item) => item.key}
                  aria-label={t("listLabel")}
                  className="gap-0.5"
                  renderItem={(item) => (
                    <StudioNotificationRow
                      item={item}
                      density="comfortable"
                      onMarkRead={() => void markOne(item.key)}
                      onOpen={() => {
                        if (!item.read) {
                          void markOne(item.key);
                        }
                      }}
                    />
                  )}
                />
                {hidden > 0 && (
                  <p className="px-4 pb-2 text-xs text-muted-foreground">
                    {t("olderUnread", { count: hidden })}
                  </p>
                )}
              </GlassCard>
            )}
          </AnimatedTabsPanel>
        ))}
      </AnimatedTabs>
    </div>
  );
}

"use client";

import { Tabs } from "@base-ui/react/tabs";
import { BellOffIcon, CheckCheckIcon, InboxIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { EmptyState, LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useNotifications } from "@/hooks/use-notifications";
import { NOTIFICATION_FILTERS, type NotificationFilter, olderUnread } from "./notification-meta";
import { NotificationRow } from "./notification-row";
import { useNotificationActions, useNotificationItems } from "./use-notification-items";

/**
 * The Classic notifications page: every current notification (the newest 50) or only the
 * unread ones, each linking to its run or project; mark one or all of them read.
 */
export function NotificationsView() {
  const t = useTranslations("notifications");
  const notifications = useNotifications();
  const { query, items, unreadCount, isMarking } = notifications;
  const { markOne, markAll } = useNotificationActions(notifications);
  const toItem = useNotificationItems("");
  const [filter, setFilter] = useState<NotificationFilter>("all");
  const listedUnread = items.filter((item) => !item.read).length;
  const hidden = olderUnread(unreadCount, listedUnread);
  const shown = (filter === "unread" ? items.filter((item) => !item.read) : items).map(toItem);

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <Button
            variant="outline"
            disabled={!unreadCount || isMarking}
            onClick={() => void markAll()}
          >
            <CheckCheckIcon aria-hidden />
            {t("markAllRead")}
          </Button>
        }
      />
      <Tabs.Root
        value={filter}
        onValueChange={(value) => setFilter(value === "unread" ? "unread" : "all")}
        className="grid gap-4"
      >
        <Tabs.List
          aria-label={t("filter.label")}
          className="inline-flex w-fit items-center gap-1 rounded-lg bg-muted p-1"
        >
          {NOTIFICATION_FILTERS.map((value) => (
            <Tabs.Tab
              key={value}
              value={value}
              className="inline-flex h-7 items-center rounded-md px-3 text-sm font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-active:bg-background data-active:text-foreground data-active:shadow-sm"
            >
              {value === "unread" && unreadCount
                ? t("filter.unreadCount", { count: unreadCount })
                : t(`filter.${value}`)}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        {NOTIFICATION_FILTERS.map((value) => (
          <Tabs.Panel
            key={value}
            value={value}
            className="rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {query.isPending ? (
              <LoadingRows rows={5} />
            ) : query.isError ? (
              <QueryError error={query.error} onRetry={() => query.refetch()} />
            ) : shown.length === 0 ? (
              value === "unread" ? (
                <EmptyState
                  icon={<BellOffIcon aria-hidden />}
                  title={t("emptyUnread")}
                  description={hidden > 0 ? t("olderUnread", { count: hidden }) : undefined}
                />
              ) : (
                <EmptyState
                  icon={<InboxIcon aria-hidden />}
                  title={t("empty")}
                  description={t("emptyDescription")}
                />
              )
            ) : (
              <Card size="sm">
                <CardContent className="grid gap-3">
                  <ul aria-label={t("listLabel")} className="grid gap-0.5">
                    {shown.map((item) => (
                      <li key={item.key}>
                        <NotificationRow
                          item={item}
                          onMarkRead={() => void markOne(item.key)}
                          onOpen={() => {
                            if (!item.read) {
                              void markOne(item.key);
                            }
                          }}
                        />
                      </li>
                    ))}
                  </ul>
                  {hidden > 0 && (
                    <p className="px-2.5 text-xs text-muted-foreground">
                      {t("olderUnread", { count: hidden })}
                    </p>
                  )}
                </CardContent>
              </Card>
            )}
          </Tabs.Panel>
        ))}
      </Tabs.Root>
    </>
  );
}

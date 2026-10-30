"use client";

import { useFormatter, useNow, useTranslations } from "next-intl";
import { useCallback } from "react";
import { toast } from "sonner";
import type { NotificationOut } from "@/client";
import { useMonthName } from "@/components/admin/admin-labels";
import { useLabels } from "@/components/runs/use-labels";
import { useErrorMessage } from "@/hooks/use-error-message";
import type { Notifications } from "@/hooks/use-notifications";
import { USD } from "@/lib/format";
import {
  describeNotification,
  type InterfacePrefix,
  type NotificationView,
} from "@/lib/notifications";

/** A notification ready for a list in either interface. */
export type NotificationItem = NotificationView & {
  key: string;
  read: boolean;
  /** The sentence to show; it also names the link. */
  text: string;
  /** The project, for the line under the sentence ("" when there is none). */
  project: string;
  /** When it happened: the API's timestamp (for `<time dateTime>`), and relative to now. */
  createdAt: string;
  time: string;
};

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

/**
 * Turns API notifications into list items for the interface with `prefix` ("" or "/studio"):
 * the translated sentence (stage names, run errors, money and months in the UI language), the
 * relative time, and everything describeNotification knows (icon, tone, link).
 */
export function useNotificationItems(
  prefix: InterfacePrefix,
): (notification: NotificationOut) => NotificationItem {
  const t = useTranslations();
  const format = useFormatter();
  const { stage: stageName, errorText } = useLabels();
  const monthName = useMonthName();
  const now = useNow({ updateInterval: 60_000 });

  return useCallback(
    (notification: NotificationOut) => {
      const view = describeNotification(notification, prefix);
      const { values } = view;
      const stage = str(values.stage);
      const error = str(values.error);
      const month = str(values.month);
      const expiresAt = values.expiresAt instanceof Date ? values.expiresAt : null;
      const project = str(values.project);
      const shown = {
        topic: str(values.topic) || t("notifications.untitled"),
        project,
        stage: stage ? stageName(stage) : t("notifications.someStage"),
        error: error ? errorText(error) : "",
        days: num(values.days),
        expiresAt: expiresAt ? format.relativeTime(expiresAt, now) : t("notifications.soon"),
        percent: format.number(num(values.percent)),
        month: month ? monthName(month) : "",
        budget: format.number(num(values.budget), USD),
        spent: format.number(num(values.spent), USD),
      };
      const created = new Date(notification.created_at);
      return {
        ...view,
        key: notification.key,
        read: notification.read,
        text: t(view.messageKey, shown).trim(),
        project,
        createdAt: notification.created_at,
        time: Number.isNaN(created.getTime()) ? "" : format.relativeTime(created, now),
      };
    },
    [prefix, t, format, stageName, errorText, monthName, now],
  );
}

/** Mark one or every notification read, with an error toast when the API refuses. */
export function useNotificationActions(notifications: Notifications) {
  const t = useTranslations("notifications");
  const errorMessage = useErrorMessage();
  const { markRead, markAllRead } = notifications;

  const markOne = useCallback(
    async (key: string) => {
      const result = await markRead([key]);
      if (!result.ok) {
        toast.error(t("markFailed"), { description: errorMessage(result.error) });
      }
    },
    [markRead, t, errorMessage],
  );

  const markAll = useCallback(async () => {
    const result = await markAllRead();
    if (!result.ok) {
      toast.error(t("markFailed"), { description: errorMessage(result.error) });
    }
  }, [markAllRead, t, errorMessage]);

  return { markOne, markAll };
}

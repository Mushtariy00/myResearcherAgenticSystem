"use client";

import { CheckIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import type { NotificationTone } from "@/lib/notifications";
import { cn } from "@/lib/utils";
import { NOTIFICATION_ICONS } from "./notification-meta";
import type { NotificationItem } from "./use-notification-items";

const TONES: Record<NotificationTone, string> = {
  neutral: "bg-muted text-muted-foreground",
  info: "bg-sky-500/15 text-sky-800 dark:text-sky-300",
  warning: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  success: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
  danger: "bg-destructive/10 text-destructive dark:bg-destructive/20",
};

export type NotificationRowProps = {
  item: NotificationItem;
  /** Called when the link is followed (mark it read, close the popover). */
  onOpen?: (item: NotificationItem) => void;
  onMarkRead: (item: NotificationItem) => void;
  marking?: boolean;
};

/**
 * One Classic notification: its icon and tone, the sentence (a link to the run or project,
 * covering the whole row), the project and time, and a "mark as read" button while unread.
 */
export function NotificationRow({
  item,
  onOpen,
  onMarkRead,
  marking = false,
}: NotificationRowProps) {
  const t = useTranslations("notifications");
  const textId = useId();
  const Icon = NOTIFICATION_ICONS[item.icon];
  const sentence = (
    <>
      {!item.read && <span className="sr-only">{t("unread")}: </span>}
      {item.text}
    </>
  );

  return (
    <div
      className={cn(
        "relative flex items-start gap-3 rounded-lg px-2.5 py-2 transition-colors has-[a:hover]:bg-muted/60",
        !item.read && "bg-primary/5",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full [&_svg]:size-4",
          TONES[item.tone],
        )}
      >
        <Icon />
      </span>
      <div className="min-w-0 flex-1">
        {item.href ? (
          <Link
            id={textId}
            href={item.href}
            onClick={() => onOpen?.(item)}
            className={cn(
              "text-sm break-words outline-none after:absolute after:inset-0 after:rounded-lg focus-visible:after:ring-3 focus-visible:after:ring-ring/50",
              !item.read && "font-medium",
            )}
          >
            {sentence}
          </Link>
        ) : (
          <p id={textId} className={cn("text-sm break-words", !item.read && "font-medium")}>
            {sentence}
          </p>
        )}
        <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted-foreground">
          {item.project && (
            <>
              <span className="truncate">{item.project}</span>
              <span aria-hidden>·</span>
            </>
          )}
          <time dateTime={item.createdAt}>{item.time}</time>
          {item.needsAction && !item.read && (
            <span className="inline-flex h-4 items-center rounded-full bg-amber-500/15 px-1.5 font-medium text-amber-800 dark:text-amber-300">
              {t("needsAction")}
            </span>
          )}
        </p>
      </div>
      {!item.read && (
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={t("markRead")}
          aria-describedby={textId}
          title={t("markRead")}
          disabled={marking}
          onClick={() => onMarkRead(item)}
          className="relative z-10 mt-1"
        >
          <CheckIcon aria-hidden />
        </Button>
      )}
    </div>
  );
}

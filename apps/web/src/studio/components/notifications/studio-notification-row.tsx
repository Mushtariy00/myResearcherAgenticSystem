"use client";

import { CheckIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { NOTIFICATION_ICONS } from "@/components/notifications/notification-meta";
import type { NotificationItem } from "@/components/notifications/use-notification-items";
import { cn } from "@/lib/utils";
import { ICON_BUTTON } from "@/studio/lib/ui";

export type StudioNotificationRowProps = {
  item: NotificationItem;
  /** Called when the link is followed (mark it read, close the popover). */
  onOpen?: (item: NotificationItem) => void;
  onMarkRead: (item: NotificationItem) => void;
  /** `compact` in the bell's popover, `comfortable` on the notifications page. */
  density?: "compact" | "comfortable";
};

/**
 * One Studio notification: a tone-coloured icon chip, the sentence (a link to the run or
 * project covering the row), the project and time, an unread dot and "mark as read".
 */
export function StudioNotificationRow({
  item,
  onOpen,
  onMarkRead,
  density = "compact",
}: StudioNotificationRowProps) {
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
        "relative flex items-start gap-3 rounded-xl transition-colors has-[a:hover]:bg-(--studio-hover)",
        density === "compact" ? "px-2.5 py-2" : "px-3 py-3 sm:px-4",
      )}
    >
      <span
        aria-hidden
        data-tone={item.tone}
        className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-(--tone)/25 bg-(--tone)/12 text-(--tone-fg) [&_svg]:size-4"
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
              "text-sm break-words text-foreground outline-none after:absolute after:inset-0 after:rounded-xl focus-visible:after:ring-3 focus-visible:after:ring-ring/50",
              !item.read && "font-medium",
            )}
          >
            {sentence}
          </Link>
        ) : (
          <p
            id={textId}
            className={cn("text-sm break-words text-foreground", !item.read && "font-medium")}
          >
            {sentence}
          </p>
        )}
        <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted-foreground">
          {item.project && (
            <>
              <span className="truncate">{item.project}</span>
              <span aria-hidden>·</span>
            </>
          )}
          <time dateTime={item.createdAt} className="tabular-nums">
            {item.time}
          </time>
          {item.needsAction && !item.read && (
            <span
              data-tone="warning"
              className="inline-flex h-4 items-center rounded-full border border-(--tone)/25 bg-(--tone)/12 px-1.5 font-medium text-(--tone-fg)"
            >
              {t("needsAction")}
            </span>
          )}
        </p>
      </div>
      {!item.read && (
        <div className="relative z-10 flex shrink-0 items-center gap-1">
          <span
            aria-hidden
            className="size-2 rounded-full bg-(--studio-accent-fg) shadow-[0_0_0_3px_color-mix(in_oklch,var(--studio-accent-fg)_18%,transparent)]"
          />
          <button
            type="button"
            aria-label={t("markRead")}
            aria-describedby={textId}
            title={t("markRead")}
            onClick={() => onMarkRead(item)}
            className={cn(ICON_BUTTON, "size-8")}
          >
            <CheckIcon aria-hidden />
          </button>
        </div>
      )}
    </div>
  );
}

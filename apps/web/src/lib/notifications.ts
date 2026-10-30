import type { NotificationList, NotificationOut } from "@/client";
import { toAmount } from "./format";
import { STUDIO_PREFIX, type UiVersion } from "./ui-version";

/**
 * Presentation of in-app notifications (GET /api/v1/me/notifications), shared by Classic and
 * Studio: which message to show, which icon and tone, and where the notification leads.
 *
 * Messages are translated by the caller with next-intl: `t(view.messageKey, view.values)` with
 * `useTranslations()` (no namespace). `values.stage` and `values.error` are raw codes (a stage
 * id, a run error code): translate them first, e.g. with `useLabels()` from
 * src/components/runs/use-labels.ts.
 */

export type NotificationKind = NotificationOut["kind"];

/** Where links point: "" for Classic pages, "/studio" for Studio pages. */
export type InterfacePrefix = "" | typeof STUDIO_PREFIX;

export function interfacePrefix(version: UiVersion): InterfacePrefix {
  return version === "studio" ? STUDIO_PREFIX : "";
}

/** lucide-react icon names (kebab-case); each interface maps them to its own components. */
export type NotificationIcon =
  | "eye"
  | "hourglass"
  | "circle-check"
  | "triangle-alert"
  | "ban"
  | "circle-x"
  | "wallet"
  | "bell";

/** The same tones as the status badges of both interfaces. */
export type NotificationTone = "neutral" | "info" | "success" | "warning" | "danger";

/** Every message key a notification can use (they belong in messages/<locale>/notifications.json). */
export const NOTIFICATION_MESSAGE_KEYS = [
  "notifications.items.approvalNeeded",
  "notifications.items.approvalExpiring",
  "notifications.items.runCompleted",
  "notifications.items.runFailed",
  "notifications.items.runCancelled",
  "notifications.items.runRejected",
  "notifications.items.runPaused",
  "notifications.items.budgetWarning",
  "notifications.items.budgetExhausted",
  "notifications.items.unknown",
] as const;

export type NotificationMessageKey = (typeof NOTIFICATION_MESSAGE_KEYS)[number];

/**
 * Values for the message, by kind:
 * - approvals: `topic`, `project`, `stage` (+ `days` and `expiresAt` when expiring);
 * - finished and paused runs: `topic`, `project` (+ `error`, a run error code or "", when failed);
 * - budget alerts: `percent` (80 or 100), `month` ("2026-10"), `budget` and `spent` (USD numbers).
 */
export type NotificationValues = Record<string, string | number | Date>;

export type NotificationView = {
  messageKey: NotificationMessageKey;
  values: NotificationValues;
  icon: NotificationIcon;
  tone: NotificationTone;
  /** The run page, else the project page, in the given interface; null when there is neither. */
  href: string | null;
  /** Someone has to act: an approval is waiting. */
  needsAction: boolean;
};

type KindMeta = {
  messageKey: NotificationMessageKey;
  icon: NotificationIcon;
  tone: NotificationTone;
};

const KINDS: Record<Exclude<NotificationKind, "budget_alert">, KindMeta> = {
  approval_needed: {
    messageKey: "notifications.items.approvalNeeded",
    icon: "eye",
    tone: "warning",
  },
  approval_expiring: {
    messageKey: "notifications.items.approvalExpiring",
    icon: "hourglass",
    tone: "danger",
  },
  run_completed: {
    messageKey: "notifications.items.runCompleted",
    icon: "circle-check",
    tone: "success",
  },
  run_failed: {
    messageKey: "notifications.items.runFailed",
    icon: "triangle-alert",
    tone: "danger",
  },
  run_cancelled: { messageKey: "notifications.items.runCancelled", icon: "ban", tone: "neutral" },
  run_rejected: { messageKey: "notifications.items.runRejected", icon: "circle-x", tone: "danger" },
  run_paused: { messageKey: "notifications.items.runPaused", icon: "wallet", tone: "warning" },
};

const UNKNOWN: KindMeta = {
  messageKey: "notifications.items.unknown",
  icon: "bell",
  tone: "neutral",
};

function text(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/** Numbers arrive as numbers or decimal strings ("12.50"); anything else reads as zero. */
const number = toAmount;

function budgetPercent(notification: NotificationOut): number {
  return number(notification.params.percent);
}

function meta(notification: NotificationOut): KindMeta {
  if (notification.kind === "budget_alert") {
    return budgetPercent(notification) >= 100
      ? { messageKey: "notifications.items.budgetExhausted", icon: "wallet", tone: "danger" }
      : { messageKey: "notifications.items.budgetWarning", icon: "wallet", tone: "warning" };
  }
  return KINDS[notification.kind] ?? UNKNOWN;
}

/** The message key of a notification. */
export function notificationMessageKey(notification: NotificationOut): NotificationMessageKey {
  return meta(notification).messageKey;
}

/** The icon name of a notification. */
export function notificationIcon(notification: NotificationOut): NotificationIcon {
  return meta(notification).icon;
}

/** The values its message interpolates (see NotificationValues). */
export function notificationValues(notification: NotificationOut): NotificationValues {
  const { params } = notification;
  switch (notification.kind) {
    case "approval_needed":
      return {
        topic: text(params.topic),
        project: text(params.project),
        stage: text(params.stage ?? notification.stage),
      };
    case "approval_expiring": {
      const expiresAt = new Date(text(params.expires_at));
      return {
        topic: text(params.topic),
        project: text(params.project),
        stage: text(params.stage ?? notification.stage),
        days: number(params.days),
        ...(Number.isNaN(expiresAt.getTime()) ? {} : { expiresAt }),
      };
    }
    case "run_completed":
    case "run_cancelled":
    case "run_rejected":
    case "run_paused":
      return { topic: text(params.topic), project: text(params.project) };
    case "run_failed":
      return {
        topic: text(params.topic),
        project: text(params.project),
        error: text(params.error),
      };
    case "budget_alert":
      return {
        percent: budgetPercent(notification),
        month: text(params.month),
        budget: number(params.budget_usd),
        spent: number(params.spent_usd),
      };
    default:
      return {};
  }
}

/**
 * Where the notification leads in the interface with `prefix`: its run, else its project, else
 * nowhere (budget alerts).
 */
export function notificationHref(
  notification: NotificationOut,
  prefix: InterfacePrefix,
): string | null {
  if (notification.run_id) {
    return `${prefix}/runs/${encodeURIComponent(notification.run_id)}`;
  }
  if (notification.project_id) {
    return `${prefix}/projects/${encodeURIComponent(notification.project_id)}`;
  }
  return null;
}

/** Everything a notification list item needs, for the interface with `prefix`. */
export function describeNotification(
  notification: NotificationOut,
  prefix: InterfacePrefix,
): NotificationView {
  const { messageKey, icon, tone } = meta(notification);
  return {
    messageKey,
    values: notificationValues(notification),
    icon,
    tone,
    href: notificationHref(notification, prefix),
    needsAction:
      notification.kind === "approval_needed" || notification.kind === "approval_expiring",
  };
}

/**
 * The list as it reads once `keys` (or every notification, for "all") are marked read: the
 * optimistic state while the request is on its way. `unread_count` covers notifications beyond
 * the listed ones, so it only drops by the listed items that change.
 */
export function withNotificationsRead(
  list: NotificationList,
  keys: readonly string[] | "all",
): NotificationList {
  if (keys === "all") {
    return { items: list.items.map((item) => ({ ...item, read: true })), unread_count: 0 };
  }
  const marking = new Set(keys);
  let changed = 0;
  const items = list.items.map((item) => {
    if (item.read || !marking.has(item.key)) {
      return item;
    }
    changed += 1;
    return { ...item, read: true };
  });
  return changed === 0 ? list : { items, unread_count: Math.max(0, list.unread_count - changed) };
}

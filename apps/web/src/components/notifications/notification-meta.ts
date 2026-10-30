import {
  BanIcon,
  BellIcon,
  CircleCheckIcon,
  CircleXIcon,
  EyeIcon,
  HourglassIcon,
  type LucideIcon,
  TriangleAlertIcon,
  WalletIcon,
} from "lucide-react";
import type { NotificationIcon } from "@/lib/notifications";

/** The lucide component for each notification icon name (both interfaces). */
export const NOTIFICATION_ICONS: Record<NotificationIcon, LucideIcon> = {
  eye: EyeIcon,
  hourglass: HourglassIcon,
  "circle-check": CircleCheckIcon,
  "triangle-alert": TriangleAlertIcon,
  ban: BanIcon,
  "circle-x": CircleXIcon,
  wallet: WalletIcon,
  bell: BellIcon,
};

/** How many notifications the bells of both interfaces list. */
export const BELL_LIMIT = 8;

/** The notifications page of each interface. */
export const NOTIFICATIONS_PATH = { classic: "/notifications", studio: "/studio/notifications" };

/** The text of an unread badge: the count, capped so it fits ("99+"). */
export function badgeCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}

/** The filters of the notifications pages. */
export const NOTIFICATION_FILTERS = ["all", "unread"] as const;
export type NotificationFilter = (typeof NOTIFICATION_FILTERS)[number];

/** Unread notifications the list cannot show: older than the newest 50 the API returns. */
export function olderUnread(unreadCount: number | null, listedUnread: number): number {
  return Math.max(0, (unreadCount ?? 0) - listedUnread);
}

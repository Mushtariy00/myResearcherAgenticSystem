import {
  ActivityIcon,
  type LucideIcon,
  RouteIcon,
  ScrollTextIcon,
  UsersIcon,
  WalletCardsIcon,
  WalletIcon,
} from "lucide-react";

/**
 * The sections (tabs) of the admin page in both interfaces. The open one is in the URL as
 * `?tab=<id>` (none for the first), so a reload or a shared link opens the same section.
 */
export const ADMIN_TABS = ["users", "budgets", "routing", "balance", "health", "audit"] as const;

export type AdminTab = (typeof ADMIN_TABS)[number];

export const DEFAULT_ADMIN_TAB: AdminTab = "users";

export const ADMIN_TAB_ICONS: Record<AdminTab, LucideIcon> = {
  users: UsersIcon,
  budgets: WalletIcon,
  routing: RouteIcon,
  balance: WalletCardsIcon,
  health: ActivityIcon,
  audit: ScrollTextIcon,
};

export function isAdminTab(value: unknown): value is AdminTab {
  return typeof value === "string" && (ADMIN_TABS as readonly string[]).includes(value);
}

/** The tab a `?tab=` value names; anything else opens the first tab. */
export function parseAdminTab(value: unknown): AdminTab {
  const first = Array.isArray(value) ? value[0] : value;
  return isAdminTab(first) ? first : DEFAULT_ADMIN_TAB;
}

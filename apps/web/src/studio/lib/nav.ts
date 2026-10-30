import {
  BellIcon,
  FolderKanbanIcon,
  LayoutDashboardIcon,
  LibraryIcon,
  type LucideIcon,
  ShieldCheckIcon,
} from "lucide-react";
import type { SessionUser } from "@/lib/session-user";
import { STUDIO_PREFIX } from "@/lib/ui-version";

export type StudioNavId = "dashboard" | "projects" | "papers" | "notifications" | "admin";

export type StudioNavItem = {
  id: StudioNavId;
  href: string;
  icon: LucideIcon;
  adminOnly?: boolean;
};

export const STUDIO_ROUTES = {
  dashboard: `${STUDIO_PREFIX}/dashboard`,
  /** Projects have no index page yet: the dashboard lists them. */
  projects: `${STUDIO_PREFIX}/dashboard#projects`,
  papers: `${STUDIO_PREFIX}/papers`,
  notifications: `${STUDIO_PREFIX}/notifications`,
  admin: `${STUDIO_PREFIX}/admin`,
} as const satisfies Record<StudioNavId, string>;

export function studioProjectPath(projectId: string): string {
  return `${STUDIO_PREFIX}/projects/${encodeURIComponent(projectId)}`;
}

export const STUDIO_NAV: readonly StudioNavItem[] = [
  { id: "dashboard", href: STUDIO_ROUTES.dashboard, icon: LayoutDashboardIcon },
  { id: "projects", href: STUDIO_ROUTES.projects, icon: FolderKanbanIcon },
  { id: "papers", href: STUDIO_ROUTES.papers, icon: LibraryIcon },
  { id: "notifications", href: STUDIO_ROUTES.notifications, icon: BellIcon },
  { id: "admin", href: STUDIO_ROUTES.admin, icon: ShieldCheckIcon, adminOnly: true },
];

/** The sidebar items this user sees (Admin only for lab admins). */
export function visibleNav(role: SessionUser["role"]): StudioNavItem[] {
  return STUDIO_NAV.filter((item) => !item.adminOnly || role === "admin");
}

function under(pathname: string, path: string): boolean {
  return pathname === path || pathname.startsWith(`${path}/`);
}

/** The sidebar item a Studio page belongs to (runs belong to their project). */
export function activeNavId(pathname: string): StudioNavId | null {
  if (pathname === STUDIO_ROUTES.dashboard) {
    return "dashboard";
  }
  if (under(pathname, `${STUDIO_PREFIX}/projects`) || under(pathname, `${STUDIO_PREFIX}/runs`)) {
    return "projects";
  }
  if (under(pathname, STUDIO_ROUTES.papers)) {
    return "papers";
  }
  if (under(pathname, STUDIO_ROUTES.notifications)) {
    return "notifications";
  }
  if (under(pathname, STUDIO_ROUTES.admin)) {
    return "admin";
  }
  return null;
}

export type CrumbLabel =
  | { kind: "nav"; id: StudioNavId }
  | { kind: "project"; id: string }
  | { kind: "run" | "paper" | "profile" }
  | { kind: "text"; text: string };

export type Crumb = { key: string; label: CrumbLabel; href?: string };

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

/**
 * The breadcrumb trail of a Studio page; the last crumb is the current page and has no link.
 * Labels are resolved by the caller (translations, project names).
 */
export function studioBreadcrumbs(pathname: string): Crumb[] {
  const rest = pathname.startsWith(STUDIO_PREFIX) ? pathname.slice(STUDIO_PREFIX.length) : pathname;
  const [section, id] = rest.split("/").filter(Boolean);
  const dashboard: Crumb = {
    key: "dashboard",
    label: { kind: "nav", id: "dashboard" },
    href: STUDIO_ROUTES.dashboard,
  };
  switch (section) {
    case undefined:
    case "dashboard":
      return [{ key: "dashboard", label: { kind: "nav", id: "dashboard" } }];
    case "projects":
      return [
        dashboard,
        {
          key: "projects",
          label: { kind: "nav", id: "projects" },
          href: id ? STUDIO_ROUTES.projects : undefined,
        },
        ...(id ? [{ key: `project:${id}`, label: { kind: "project", id } } satisfies Crumb] : []),
      ];
    case "runs":
      return [dashboard, { key: "run", label: { kind: "run" } }];
    case "papers":
      return [
        {
          key: "papers",
          label: { kind: "nav", id: "papers" },
          href: id ? STUDIO_ROUTES.papers : undefined,
        },
        ...(id ? [{ key: `paper:${id}`, label: { kind: "paper" } } satisfies Crumb] : []),
      ];
    case "notifications":
      return [{ key: "notifications", label: { kind: "nav", id: "notifications" } }];
    case "admin":
      return [{ key: "admin", label: { kind: "nav", id: "admin" } }];
    case "profile":
      return [{ key: "profile", label: { kind: "profile" } }];
    default:
      return [{ key: section, label: { kind: "text", text: decodeSegment(section) } }];
  }
}

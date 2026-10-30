import { STUDIO_PREFIX } from "@/lib/ui-version";

export const STUDIO_LOGIN_PATH = `${STUDIO_PREFIX}/login`;
export const STUDIO_DASHBOARD_PATH = `${STUDIO_PREFIX}/dashboard`;

/**
 * The Studio sign-in page that brings the visitor back to where they were (`?next=`), the same
 * rule as proxy.ts: the dashboard is where sign-in lands anyway, so it needs no `next`.
 */
export function studioLoginHref(pathname: string, search = ""): string {
  if (pathname === STUDIO_DASHBOARD_PATH || pathname === STUDIO_PREFIX) {
    return STUDIO_LOGIN_PATH;
  }
  const query = search && !search.startsWith("?") ? `?${search}` : search;
  return `${STUDIO_LOGIN_PATH}?next=${encodeURIComponent(`${pathname}${query}`)}`;
}

/**
 * The app ships two interfaces over the same data and API: Classic (today's URLs) and Studio
 * (an animated design under /studio). These helpers map a page to its twin in the other version.
 * Studio's own home (/studio) is a public landing page; its dashboard is /studio/dashboard.
 */
export const STUDIO_PREFIX = "/studio";

export type UiVersion = "classic" | "studio";

export function uiVersionOf(pathname: string): UiVersion {
  return pathname === STUDIO_PREFIX || pathname.startsWith(`${STUDIO_PREFIX}/`)
    ? "studio"
    : "classic";
}

export function toStudioPath(pathname: string): string {
  if (uiVersionOf(pathname) === "studio") {
    return pathname;
  }
  return pathname === "/" ? `${STUDIO_PREFIX}/dashboard` : `${STUDIO_PREFIX}${pathname}`;
}

export function toClassicPath(pathname: string): string {
  if (uiVersionOf(pathname) === "classic") {
    return pathname;
  }
  const rest = pathname.slice(STUDIO_PREFIX.length);
  return rest === "" || rest === "/" || rest === "/dashboard" ? "/" : rest;
}

const PUBLIC_PATHS = ["/login", "/reset-password", "/studio/login", "/studio/reset-password"];

/** Pages anyone may open, in both versions. Everything else needs a session. */
export function isPublicPath(pathname: string): boolean {
  return (
    pathname === STUDIO_PREFIX ||
    PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))
  );
}

/** The sign-in page of the version the visitor is in. */
export function loginPathFor(pathname: string): string {
  return uiVersionOf(pathname) === "studio" ? `${STUDIO_PREFIX}/login` : "/login";
}

/**
 * The sign-in page that brings the visitor back to the page (`?next=`, which the sign-in page
 * checks with safeNextPath). The dashboards need no `next`: sign-in lands there anyway.
 */
export function signInHref(pathname: string, search = ""): string {
  const login = loginPathFor(pathname);
  if (pathname === "/" || pathname === STUDIO_PREFIX || pathname === `${STUDIO_PREFIX}/dashboard`) {
    return login;
  }
  const query = search && !search.startsWith("?") ? `?${search}` : search;
  return `${login}?next=${encodeURIComponent(`${pathname}${query}`)}`;
}

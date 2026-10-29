import { getSessionCookie } from "better-auth/cookies";
import { type NextRequest, NextResponse } from "next/server";

/** Pages anyone may open. Everything else needs a session cookie. */
const PUBLIC_PATHS = ["/login", "/reset-password"];

/**
 * Optimistic gate: without a session cookie, protected pages redirect to /login before
 * rendering. The (app) layout then verifies the session itself, and FastAPI checks every
 * API call, so a forged or expired cookie gets no further than this.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return NextResponse.next();
  }
  if (getSessionCookie(request)) {
    return NextResponse.next();
  }
  const login = new URL("/login", request.url);
  if (pathname !== "/") {
    login.searchParams.set("next", `${pathname}${search}`);
  }
  return NextResponse.redirect(login);
}

export const config = {
  // Skip API routes (Better Auth, and /api/v1 which Caddy sends to FastAPI), assets and files.
  matcher: ["/((?!api/|_next/|favicon.ico|.*\\.[a-zA-Z0-9]+$).*)"],
};

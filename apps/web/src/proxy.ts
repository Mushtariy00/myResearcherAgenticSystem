import { getSessionCookie } from "better-auth/cookies";
import { type NextRequest, NextResponse } from "next/server";
import { isPublicPath, loginPathFor } from "@/lib/ui-version";

/**
 * Optimistic gate: without a session cookie, protected pages redirect to the sign-in page of
 * their version (Classic or Studio) before rendering. The (app) layouts then verify the session
 * themselves, and FastAPI checks every API call, so a forged or expired cookie gets no further.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (isPublicPath(pathname) || getSessionCookie(request)) {
    return NextResponse.next();
  }
  const login = new URL(loginPathFor(pathname), request.url);
  if (pathname !== "/" && pathname !== "/studio/dashboard") {
    login.searchParams.set("next", `${pathname}${search}`);
  }
  return NextResponse.redirect(login);
}

export const config = {
  // Skip API routes (Better Auth, and /api/v1 which Caddy sends to FastAPI), assets and files.
  matcher: ["/((?!api/|_next/|favicon.ico|.*\\.[a-zA-Z0-9]+$).*)"],
};

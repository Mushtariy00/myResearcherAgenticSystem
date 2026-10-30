import { getSessionCookie } from "better-auth/cookies";
import { type NextRequest, NextResponse } from "next/server";
import { contentSecurityPolicy, newNonce } from "@/lib/csp";
import { isPublicPath, loginPathFor } from "@/lib/ui-version";

/**
 * Two jobs before a page renders:
 * - An optimistic gate: without a session cookie, protected pages redirect to the sign-in page
 *   of their version (Classic or Studio). The (app) layouts then verify the session themselves,
 *   and FastAPI checks every API call, so a forged or expired cookie gets no further.
 * - The page's Content-Security-Policy with a fresh nonce. Next.js reads the nonce from the
 *   request's policy header and puts it on its scripts; the root layout reads `x-nonce`.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (!isPublicPath(pathname) && !getSessionCookie(request)) {
    const login = new URL(loginPathFor(pathname), request.url);
    if (pathname !== "/" && pathname !== "/studio/dashboard") {
      login.searchParams.set("next", `${pathname}${search}`);
    }
    return NextResponse.redirect(login);
  }
  const nonce = newNonce();
  const policy = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  // Skip API routes (Better Auth, and /api/v1 which Caddy sends to FastAPI), assets and files.
  matcher: ["/((?!api/|_next/|favicon.ico|.*\\.[a-zA-Z0-9]+$).*)"],
};

/**
 * Sending the user to sign in after an API 401, without looping. FastAPI caches session checks
 * for up to a minute, so it can keep answering 401 for a session Better Auth accepts again (it
 * failed for a moment, say). The sign-in page then finds the session valid and sends the user
 * straight back, where the next 401 would start over. So a tab is sent at most once per window,
 * until a sign-in succeeds.
 */

import { toApiError } from "./api-error";
import { signInHref } from "./ui-version";

const STORAGE_KEY = "arp:sign-in-redirect";

/** Longer than FastAPI's session cache (60 s), so its stale answer has expired by then. */
export const SIGN_IN_REDIRECT_WINDOW_MS = 90_000;

function lastRedirect(): number | null {
  try {
    const value = Number(window.sessionStorage.getItem(STORAGE_KEY));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

/**
 * Whether a 401 should send this tab to the sign-in page now; if so, the time is noted. False
 * while an earlier redirect is recent: the user came back from the sign-in page without signing
 * in, because it found a valid session.
 */
export function claimSignInRedirect(now: number = Date.now()): boolean {
  const last = lastRedirect();
  if (last !== null && now - last >= 0 && now - last < SIGN_IN_REDIRECT_WINDOW_MS) {
    return false;
  }
  try {
    window.sessionStorage.setItem(STORAGE_KEY, String(now));
  } catch {
    // Without storage there is no loop guard, only the redirect.
  }
  return true;
}

/** After a successful sign-in, the next 401 means the session ended again. */
export function resetSignInRedirect(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing was stored.
  }
}

/**
 * Where a failed API call sends the user: after a 401, the sign-in page of their interface,
 * which brings them back to `page` (once per window, see claimSignInRedirect); otherwise
 * nowhere (null).
 */
export function signInRedirectFor(
  error: unknown,
  page: { pathname: string; search: string },
): string | null {
  if (toApiError(error).status !== 401 || !claimSignInRedirect()) {
    return null;
  }
  return signInHref(page.pathname, page.search);
}

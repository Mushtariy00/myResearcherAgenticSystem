"use client";

import { redirect, usePathname, useSearchParams } from "next/navigation";
import { signInHref } from "@/lib/ui-version";

/**
 * Rendered by the Classic app layout when the session cookie is there but its session is not
 * (revoked, or expired in the database). Layouts cannot read the URL, so this client component
 * sends the visitor to sign in with `?next=` for the page they opened; `redirect` answers the
 * first page load with an HTTP redirect and acts as a client-side replace after a navigation.
 */
export function LoginRedirect(): never {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  redirect(signInHref(pathname, search));
}

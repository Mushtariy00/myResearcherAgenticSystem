"use client";

import { redirect, usePathname, useSearchParams } from "next/navigation";
import { studioLoginHref } from "@/studio/lib/login-redirect";

/**
 * Rendered by the Studio app layout when the session is missing or no longer valid. Only a
 * client component can read the current URL, and `redirect` here still answers the first page
 * load with an HTTP redirect (it runs during server rendering) and acts as a client-side
 * replace after a navigation. The sign-in page then sends the visitor back (`?next=`).
 */
export function StudioLoginRedirect(): never {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  redirect(studioLoginHref(pathname, search));
}

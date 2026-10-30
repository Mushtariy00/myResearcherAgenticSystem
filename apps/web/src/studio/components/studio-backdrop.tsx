"use client";

import { usePathname } from "next/navigation";
import { STUDIO_PREFIX } from "@/lib/ui-version";
import { AuroraBackground } from "./effects/aurora-background";

const AUTH_PATHS = [`${STUDIO_PREFIX}/login`, `${STUDIO_PREFIX}/reset-password`];

/**
 * The aurora behind every Studio page: vivid on the landing page, quiet behind working
 * screens. Sign-in pages draw their own aurora panel instead (split screen), so there is never
 * more than one set of blobs moving.
 */
export function StudioBackdrop() {
  const pathname = usePathname();
  if (AUTH_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return null;
  }
  return <AuroraBackground fixed variant={pathname === STUDIO_PREFIX ? "vivid" : "subtle"} />;
}

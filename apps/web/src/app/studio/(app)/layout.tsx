import type { ReactNode } from "react";
import { CurrentUserProvider } from "@/components/app/current-user";
import { SessionRefresh } from "@/components/app/session-refresh";
import { getSession } from "@/lib/session";
import { toSessionUser } from "@/lib/session-user";
import { StudioLoginRedirect } from "@/studio/components/shell/studio-login-redirect";
import { StudioShell } from "@/studio/components/shell/studio-shell";

/**
 * Every Studio app page needs a valid Better Auth session (the proxy only checks a cookie), as in
 * the Classic (app) layout. Without one the visitor goes to the Studio sign-in page, which brings
 * them back here: layouts cannot read the URL, so a small client component adds `?next=`.
 */
export default async function StudioAppLayout({ children }: { children: ReactNode }) {
  const session = await getSession();
  if (!session) {
    return <StudioLoginRedirect />;
  }
  return (
    <CurrentUserProvider user={toSessionUser(session.user)}>
      <SessionRefresh />
      <StudioShell>{children}</StudioShell>
    </CurrentUserProvider>
  );
}

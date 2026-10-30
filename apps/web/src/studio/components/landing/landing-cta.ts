import { STUDIO_DASHBOARD_PATH, STUDIO_LOGIN_PATH } from "@/studio/lib/login-redirect";

export type LandingCta = { href: string; label: string };

/** Signed-in visitors go straight to their dashboard; everyone else is offered sign-in. */
export function landingCta(
  signedIn: boolean,
  labels: { signIn: string; openDashboard: string },
): LandingCta {
  return signedIn
    ? { href: STUDIO_DASHBOARD_PATH, label: labels.openDashboard }
    : { href: STUDIO_LOGIN_PATH, label: labels.signIn };
}

import "server-only";
import { auth } from "./auth.ts";
import { captureSetPasswordLink, type SetPasswordPurpose } from "./reset-link.ts";
import { revokeSetPasswordLinks } from "./set-password-links.ts";

export type SetPasswordLink = {
  /** Single-use link that expires (Better Auth's reset-password flow). */
  url: string;
  /** False when SMTP is not configured or refused the message; the admin copies the link. */
  emailed: boolean;
};

/**
 * Issues a set-password link for an existing user, emails it, and returns it for the admin.
 * The link opens `/api/auth/reset-password/<token>`, which checks the token and redirects to
 * `/reset-password?token=...`. Earlier links of the user stop working: a lost invite may sit in
 * a chat or an old email.
 */
export async function issueSetPasswordLink(
  email: string,
  purpose: SetPasswordPurpose,
): Promise<SetPasswordLink | null> {
  const context = await auth.$context;
  const found = await context.internalAdapter.findUserByEmail(email);
  if (found) {
    await revokeSetPasswordLinks(context.adapter, found.user.id);
  }
  const capture = await captureSetPasswordLink(purpose, () =>
    auth.api.requestPasswordReset({ body: { email, redirectTo: "/reset-password" } }),
  );
  return capture.url ? { url: capture.url, emailed: capture.emailed } : null;
}

/** A throwaway password nobody knows; the invitee replaces it through the link. */
export function randomPassword(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Buffer.from(bytes).toString("base64url");
}

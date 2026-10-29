import { AsyncLocalStorage } from "node:async_hooks";

export type SetPasswordPurpose = "invite" | "reset";

/** What the reset-password hook saw while it ran inside `captureSetPasswordLink`. */
export type SetPasswordCapture = {
  purpose: SetPasswordPurpose;
  url?: string;
  emailed: boolean;
};

const captures = new AsyncLocalStorage<SetPasswordCapture>();

/** The capture for the current call, if an admin action is waiting for the link. */
export function currentSetPasswordCapture(): SetPasswordCapture | undefined {
  return captures.getStore();
}

/**
 * Runs `issue` (which triggers Better Auth's reset-password email hook) and returns the link the
 * hook produced, so an admin can copy it when email is not available.
 */
export async function captureSetPasswordLink(
  purpose: SetPasswordPurpose,
  issue: () => Promise<unknown>,
): Promise<SetPasswordCapture> {
  const capture: SetPasswordCapture = { purpose, emailed: false };
  await captures.run(capture, issue);
  return capture;
}

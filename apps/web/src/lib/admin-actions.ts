"use server";

import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { issueSetPasswordLink, randomPassword } from "@/lib/invites";

/** A set-password link for the admin to share, or a Better Auth error code to translate. */
export type LinkResult = { ok: true; url: string; emailed: boolean } | { ok: false; code: string };

const EMAIL = /^[^@\s]+@[^@\s]+$/;

/** The caller's request headers when they belong to a lab admin; null otherwise. */
async function adminRequestHeaders(): Promise<Headers | null> {
  const requestHeaders = await headers();
  const session = await auth.api.getSession({ headers: requestHeaders });
  return session?.user.role === "admin" ? requestHeaders : null;
}

function betterAuthCode(error: unknown): string {
  if (error && typeof error === "object" && "body" in error) {
    const code = (error as { body?: { code?: unknown } }).body?.code;
    if (typeof code === "string") {
      return code;
    }
  }
  return "UNKNOWN";
}

/**
 * Invites a lab member: creates the account with a random password nobody knows, then issues a
 * single-use, expiring set-password link (emailed, and returned so the admin can share it).
 */
export async function inviteUser(input: {
  name: string;
  email: string;
  role: string;
}): Promise<LinkResult> {
  const requestHeaders = await adminRequestHeaders();
  if (!requestHeaders) {
    return { ok: false, code: "YOU_ARE_NOT_ALLOWED_TO_CREATE_USERS" };
  }
  const name = String(input?.name ?? "").trim();
  const email = String(input?.email ?? "")
    .trim()
    .toLowerCase();
  const role = input?.role === "admin" ? "admin" : "user";
  if (!EMAIL.test(email) || email.length > 320) {
    return { ok: false, code: "INVALID_EMAIL" };
  }
  if (name.length === 0 || name.length > 200) {
    return { ok: false, code: "UNKNOWN" };
  }
  try {
    // With the admin's headers, Better Auth re-checks that this session may create users.
    await auth.api.createUser({
      body: { name, email, password: randomPassword(), role },
      headers: requestHeaders,
    });
  } catch (error) {
    return { ok: false, code: betterAuthCode(error) };
  }
  const link = await issueSetPasswordLink(email, "invite");
  return link ? { ok: true, ...link } : { ok: false, code: "UNKNOWN" };
}

/** A fresh set-password link for an existing user (lost invite or forgotten password). */
export async function sendPasswordLink(input: { email: string }): Promise<LinkResult> {
  const requestHeaders = await adminRequestHeaders();
  if (!requestHeaders) {
    return { ok: false, code: "YOU_ARE_NOT_ALLOWED_TO_LIST_USERS" };
  }
  const email = String(input?.email ?? "")
    .trim()
    .toLowerCase();
  if (!EMAIL.test(email)) {
    return { ok: false, code: "INVALID_EMAIL" };
  }
  const link = await issueSetPasswordLink(email, "reset");
  return link ? { ok: true, ...link } : { ok: false, code: "USER_NOT_FOUND" };
}

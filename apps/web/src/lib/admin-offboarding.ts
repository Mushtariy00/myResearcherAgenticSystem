"use server";

import { headers } from "next/headers";
import { auth } from "@/lib/auth";

/**
 * Offboarding for lab admins, through the Better Auth admin plugin: suspend an account (a ban,
 * which also ends every session), restore it, or only sign someone out everywhere. Each action
 * checks that the caller is a lab admin, and Better Auth checks it again with their headers.
 *
 * FastAPI caches session checks for up to 60 s, so API calls of a signed-out user stop within
 * a minute.
 */

/** Done, or a code to translate (a Better Auth error code, or OWN_ACCOUNT). */
export type OffboardingResult = { ok: true } | { ok: false; code: string };

type AdminCaller = { headers: Headers; userId: string; email: string };

/** The caller's request headers and identity when they are a lab admin; null otherwise. */
async function adminCaller(): Promise<AdminCaller | null> {
  const requestHeaders = await headers();
  const session = await auth.api.getSession({ headers: requestHeaders });
  if (session?.user.role !== "admin") {
    return null;
  }
  return { headers: requestHeaders, userId: session.user.id, email: session.user.email };
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

function targetUserId(input: { userId?: unknown } | null | undefined): string | null {
  const userId = typeof input?.userId === "string" ? input.userId.trim() : "";
  return userId.length > 0 && userId.length <= 200 ? userId : null;
}

/** Bans the account (no more sign-ins) and ends all its sessions. Reversible: restoreUser. */
export async function suspendUser(input: { userId: string }): Promise<OffboardingResult> {
  const caller = await adminCaller();
  if (!caller) {
    return { ok: false, code: "YOU_ARE_NOT_ALLOWED_TO_BAN_USERS" };
  }
  const userId = targetUserId(input);
  if (!userId) {
    return { ok: false, code: "USER_NOT_FOUND" };
  }
  if (userId === caller.userId) {
    return { ok: false, code: "OWN_ACCOUNT" };
  }
  try {
    await auth.api.banUser({
      body: { userId, banReason: `Suspended by ${caller.email}` },
      headers: caller.headers,
    });
    // The ban already ends the sessions; revoking them again keeps that guarantee explicit.
    await auth.api.revokeUserSessions({ body: { userId }, headers: caller.headers });
  } catch (error) {
    return { ok: false, code: betterAuthCode(error) };
  }
  return { ok: true };
}

/** Lifts a suspension: the person can sign in again with their password. */
export async function restoreUser(input: { userId: string }): Promise<OffboardingResult> {
  const caller = await adminCaller();
  if (!caller) {
    return { ok: false, code: "YOU_ARE_NOT_ALLOWED_TO_BAN_USERS" };
  }
  const userId = targetUserId(input);
  if (!userId) {
    return { ok: false, code: "USER_NOT_FOUND" };
  }
  try {
    await auth.api.unbanUser({ body: { userId }, headers: caller.headers });
  } catch (error) {
    return { ok: false, code: betterAuthCode(error) };
  }
  return { ok: true };
}

/** Ends every session of the account (a lost laptop, say); the password keeps working. */
export async function signOutEverywhere(input: { userId: string }): Promise<OffboardingResult> {
  const caller = await adminCaller();
  if (!caller) {
    return { ok: false, code: "YOU_ARE_NOT_ALLOWED_TO_REVOKE_USERS_SESSIONS" };
  }
  const userId = targetUserId(input);
  if (!userId) {
    return { ok: false, code: "USER_NOT_FOUND" };
  }
  if (userId === caller.userId) {
    // It would end this very session too; the profile page signs out the other devices instead.
    return { ok: false, code: "OWN_ACCOUNT" };
  }
  try {
    await auth.api.revokeUserSessions({ body: { userId }, headers: caller.headers });
  } catch (error) {
    return { ok: false, code: betterAuthCode(error) };
  }
  return { ok: true };
}

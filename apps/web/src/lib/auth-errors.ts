/** Better Auth error codes the UI translates under `auth.errors.*`. */
export const AUTH_ERROR_CODES = [
  "INVALID_EMAIL_OR_PASSWORD",
  "INVALID_EMAIL",
  "INVALID_TOKEN",
  "TOKEN_EXPIRED",
  "PASSWORD_TOO_SHORT",
  "PASSWORD_TOO_LONG",
  "USER_ALREADY_EXISTS",
  "USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL",
  "BANNED_USER",
  "USER_NOT_FOUND",
  "INVALID_ORIGIN",
  "MISSING_OR_NULL_ORIGIN",
  "YOU_ARE_NOT_ALLOWED_TO_CREATE_USERS",
  "YOU_ARE_NOT_ALLOWED_TO_LIST_USERS",
  "TOO_MANY_REQUESTS",
  "UNKNOWN",
] as const;

export type AuthErrorCode = (typeof AUTH_ERROR_CODES)[number];

const KNOWN_AUTH_CODES = new Set<string>(AUTH_ERROR_CODES);

/** Maps a Better Auth error (`{ code, status }`) to its `auth.errors.*` message key. */
export function authErrorKey(
  error: { code?: string | undefined; status?: number | undefined } | null | undefined,
): AuthErrorCode {
  if (!error) {
    return "UNKNOWN";
  }
  if (error.status === 429) {
    return "TOO_MANY_REQUESTS"; // Better Auth's rate limiter answers without a code
  }
  if (error.code && KNOWN_AUTH_CODES.has(error.code)) {
    return error.code as AuthErrorCode;
  }
  return "UNKNOWN";
}

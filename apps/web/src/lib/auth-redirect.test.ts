// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "./api-error";
import {
  claimSignInRedirect,
  resetSignInRedirect,
  SIGN_IN_REDIRECT_WINDOW_MS,
  signInRedirectFor,
} from "./auth-redirect";

const RUN_PAGE = {
  pathname: "/runs/22222222-2222-4222-8222-222222222222",
  search: "?stage=method",
};

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("claimSignInRedirect", () => {
  it("sends a tab to sign in once per window, until a sign-in succeeds", () => {
    const start = 1_000_000;
    expect(claimSignInRedirect(start)).toBe(true);
    // Back from the sign-in page within a minute: its session check found a valid session.
    expect(claimSignInRedirect(start + 5_000)).toBe(false);
    expect(claimSignInRedirect(start + SIGN_IN_REDIRECT_WINDOW_MS)).toBe(true);

    resetSignInRedirect();
    expect(claimSignInRedirect(start + SIGN_IN_REDIRECT_WINDOW_MS + 1)).toBe(true);
  });
});

describe("signInRedirectFor", () => {
  it("sends the user to sign in and back, but not round and round", () => {
    const unauthorized = new ApiError("auth.required", 401);
    expect(signInRedirectFor(unauthorized, RUN_PAGE)).toBe(
      "/login?next=%2Fruns%2F22222222-2222-4222-8222-222222222222%3Fstage%3Dmethod",
    );
    // The sign-in page sent the user straight back and the API still says 401 (its cache).
    expect(signInRedirectFor(unauthorized, RUN_PAGE)).toBeNull();
    expect(signInRedirectFor(unauthorized, RUN_PAGE)).toBeNull();

    // After signing in, a session that ends again sends the user to sign in again.
    resetSignInRedirect();
    expect(signInRedirectFor(unauthorized, { pathname: "/studio/papers", search: "" })).toBe(
      "/studio/login?next=%2Fstudio%2Fpapers",
    );
  });

  it("ignores every other failure", () => {
    expect(signInRedirectFor(new ApiError("permission.denied", 403), RUN_PAGE)).toBeNull();
    expect(signInRedirectFor(new ApiError("server.error", 502), RUN_PAGE)).toBeNull();
    expect(signInRedirectFor(new TypeError("Failed to fetch"), RUN_PAGE)).toBeNull();
    // None of them used up the redirect.
    expect(signInRedirectFor(new ApiError("auth.required", 401), RUN_PAGE)).not.toBeNull();
  });
});

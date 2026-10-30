import { describe, expect, it } from "vitest";
import {
  isPublicPath,
  loginPathFor,
  signInHref,
  toClassicPath,
  toStudioPath,
  uiVersionOf,
} from "./ui-version";

describe("ui versions", () => {
  it("tells the versions apart without matching look-alike paths", () => {
    expect(uiVersionOf("/studio")).toBe("studio");
    expect(uiVersionOf("/studio/runs/1")).toBe("studio");
    expect(uiVersionOf("/studios")).toBe("classic");
    expect(uiVersionOf("/runs/1")).toBe("classic");
  });

  it.each([
    ["/", "/studio/dashboard"],
    ["/runs/abc", "/studio/runs/abc"],
    ["/projects/p1", "/studio/projects/p1"],
    ["/login", "/studio/login"],
    ["/studio/admin", "/studio/admin"],
  ])("maps classic %s to studio %s", (classic, studio) => {
    expect(toStudioPath(classic)).toBe(studio);
  });

  it.each([
    ["/studio", "/"],
    ["/studio/", "/"],
    ["/studio/dashboard", "/"],
    ["/studio/runs/abc", "/runs/abc"],
    ["/studio/login", "/login"],
    ["/admin", "/admin"],
  ])("maps studio %s to classic %s", (studio, classic) => {
    expect(toClassicPath(studio)).toBe(classic);
  });

  it("round-trips every app page", () => {
    for (const path of ["/", "/runs/abc", "/projects/p1", "/admin", "/papers", "/login"]) {
      expect(toClassicPath(toStudioPath(path))).toBe(path);
    }
  });

  it("keeps only sign-in pages and the Studio landing page public", () => {
    for (const path of [
      "/login",
      "/reset-password",
      "/studio",
      "/studio/login",
      "/studio/reset-password/x",
    ]) {
      expect(isPublicPath(path), path).toBe(true);
    }
    for (const path of [
      "/",
      "/runs/1",
      "/studio/dashboard",
      "/studio/runs/1",
      "/studiox",
      "/loginx",
    ]) {
      expect(isPublicPath(path), path).toBe(false);
    }
  });

  it("sends visitors to the sign-in page of their version", () => {
    expect(loginPathFor("/runs/1")).toBe("/login");
    expect(loginPathFor("/studio/runs/1")).toBe("/studio/login");
  });

  it("brings visitors back to the page they opened after signing in", () => {
    expect(signInHref("/runs/1", "?stage=method")).toBe("/login?next=%2Fruns%2F1%3Fstage%3Dmethod");
    expect(signInHref("/projects/p1", "tab=members")).toBe(
      "/login?next=%2Fprojects%2Fp1%3Ftab%3Dmembers",
    );
    expect(signInHref("/studio/papers")).toBe("/studio/login?next=%2Fstudio%2Fpapers");
    // Sign-in lands on the dashboards anyway.
    expect(signInHref("/")).toBe("/login");
    expect(signInHref("/studio/dashboard", "?x=1")).toBe("/studio/login");
  });
});

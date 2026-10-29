import { describe, expect, it } from "vitest";
import { safeNextPath } from "./safe-redirect";

describe("safeNextPath", () => {
  it("allows paths inside the app", () => {
    expect(safeNextPath("/runs/123")).toBe("/runs/123");
    expect(safeNextPath("/projects/abc?tab=runs#members")).toBe("/projects/abc?tab=runs#members");
  });

  it("refuses anything that could leave the site", () => {
    for (const value of [
      "https://evil.example",
      "//evil.example/path",
      "/\\evil.example",
      "javascript:alert(1)",
      "/ok\nLocation: https://evil.example",
      "/ok\tx",
      " /runs/1",
    ]) {
      expect(safeNextPath(value), value).toBe("/");
    }
  });

  it("keeps percent-encoded characters encoded (they stay part of the path)", () => {
    expect(safeNextPath("/%0d%0aSet-Cookie:x")).toBe("/%0d%0aSet-Cookie:x");
  });

  it("does not loop back to the login page or into API routes", () => {
    expect(safeNextPath("/login")).toBe("/");
    expect(safeNextPath("/api/auth/sign-out")).toBe("/");
  });

  it("uses the fallback when nothing is given", () => {
    expect(safeNextPath(undefined)).toBe("/");
    expect(safeNextPath("", "/admin")).toBe("/admin");
  });
});

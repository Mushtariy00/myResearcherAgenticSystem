import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

const revoke = vi.hoisted(() => vi.fn(async () => 1));
vi.mock("./set-password-links.ts", () => ({ revokeSetPasswordLinks: revoke }));
// No database, no native argon2, no mail: only the configuration is under test.
vi.mock("pg", () => ({
  Pool: class {
    connect = vi.fn();
    query = vi.fn();
    end = vi.fn();
    on = vi.fn();
  },
}));
vi.mock("./password.ts", () => ({ hashPassword: vi.fn(), verifyPassword: vi.fn() }));
vi.mock("./auth-emails.ts", () => ({ sendSetPasswordEmail: vi.fn(async () => false) }));

beforeAll(() => {
  process.env.AUTH_DATABASE_URL = "postgresql://test@127.0.0.1:1/test";
  process.env.BETTER_AUTH_URL = "http://localhost:8080";
  process.env.BETTER_AUTH_SECRET = "a-test-secret-that-is-long-enough-for-better-auth";
  // Better Auth checks the database schema when it starts; there is no database here.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterAll(() => {
  vi.restoreAllMocks();
});

describe("the Better Auth configuration", () => {
  it("renews sessions only on the browser's POST, where the new cookie can be set", async () => {
    const { auth } = await import("./auth");
    expect(auth.options.session?.deferSessionRefresh).toBe(true);
  });

  it("retires every other set-password link once one is used", async () => {
    const { auth } = await import("./auth");
    const context = await auth.$context;
    await auth.options.emailAndPassword?.onPasswordReset?.({ user: { id: "user-bob" } } as never);
    expect(revoke).toHaveBeenCalledWith(context.adapter, "user-bob");
  });
});

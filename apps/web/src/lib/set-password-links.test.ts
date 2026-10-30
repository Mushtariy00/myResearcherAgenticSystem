import { beforeEach, describe, expect, it, vi } from "vitest";
import { revokeSetPasswordLinks } from "./set-password-links";

const betterAuth = vi.hoisted(() => {
  const steps: string[] = [];
  return {
    steps,
    findUserByEmail: vi.fn(async (email: string) =>
      email === "bob@lab.example" ? { user: { id: "user-bob", email }, accounts: [] } : null,
    ),
    deleteMany: vi.fn(async () => {
      steps.push("revoke earlier links");
      return 2;
    }),
    requestPasswordReset: vi.fn(async () => {
      steps.push("issue a new link");
      return { status: true };
    }),
  };
});

vi.mock("server-only", () => ({}));
vi.mock("./auth.ts", () => ({
  auth: {
    $context: Promise.resolve({
      internalAdapter: { findUserByEmail: betterAuth.findUserByEmail },
      adapter: { deleteMany: betterAuth.deleteMany },
    }),
    api: { requestPasswordReset: betterAuth.requestPasswordReset },
  },
}));

beforeEach(() => {
  betterAuth.steps.length = 0;
  vi.clearAllMocks();
});

describe("revokeSetPasswordLinks", () => {
  it("deletes the user's reset rows, found by the user id they store", async () => {
    const store = { deleteMany: vi.fn(async () => 3) };
    expect(await revokeSetPasswordLinks(store, "user-ada")).toBe(3);
    expect(store.deleteMany).toHaveBeenCalledWith({
      model: "verification",
      where: [{ field: "value", value: "user-ada" }],
    });
  });
});

describe("issueSetPasswordLink", () => {
  it("retires the earlier links before it issues a new one", async () => {
    const { issueSetPasswordLink } = await import("./invites");
    await issueSetPasswordLink("bob@lab.example", "reset");
    expect(betterAuth.deleteMany).toHaveBeenCalledWith({
      model: "verification",
      where: [{ field: "value", value: "user-bob" }],
    });
    expect(betterAuth.steps).toEqual(["revoke earlier links", "issue a new link"]);
  });

  it("leaves the database alone for an email nobody has", async () => {
    const { issueSetPasswordLink } = await import("./invites");
    expect(await issueSetPasswordLink("nobody@lab.example", "reset")).toBeNull();
    expect(betterAuth.deleteMany).not.toHaveBeenCalled();
  });
});

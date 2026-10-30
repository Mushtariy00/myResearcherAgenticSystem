import { describe, expect, it } from "vitest";
import { canSteerRun, projectPermissions } from "./permissions";

const user = { id: "me", role: "user" as const };
const admin = { id: "boss", role: "admin" as const };

describe("projectPermissions", () => {
  it("lets owners and researchers start runs, and only owners manage", () => {
    expect(projectPermissions(user, "owner")).toEqual({ canStartRuns: true, canManage: true });
    expect(projectPermissions(user, "researcher")).toEqual({
      canStartRuns: true,
      canManage: false,
    });
    expect(projectPermissions(user, "viewer")).toEqual({ canStartRuns: false, canManage: false });
    expect(projectPermissions(user, null)).toEqual({ canStartRuns: false, canManage: false });
  });

  it("lets lab admins do everything, member or not", () => {
    expect(projectPermissions(admin, null)).toEqual({ canStartRuns: true, canManage: true });
  });
});

describe("canSteerRun", () => {
  it("follows the API's can_steer: admins, owners, and researchers on their own runs", () => {
    const mine = { owner_id: "me" };
    const theirs = { owner_id: "someone-else" };
    expect(canSteerRun(admin, null, theirs)).toBe(true);
    expect(canSteerRun(user, "owner", theirs)).toBe(true);
    expect(canSteerRun(user, "researcher", mine)).toBe(true);
    expect(canSteerRun(user, "researcher", theirs)).toBe(false);
    expect(canSteerRun(user, "viewer", mine)).toBe(false);
    expect(canSteerRun(user, undefined, mine)).toBe(false);
  });
});

import type { ProjectRole, RunOut } from "@/client";
import type { SessionUser } from "@/lib/session-user";

/**
 * What the signed-in user may do in a project (docs/PLAN.md, Permissions). The API enforces the
 * same rules on every call; the UI only hides or disables what would be refused.
 */
export type ProjectPermissions = {
  /** Owners and researchers start runs (charged to their own budget); lab admins too. */
  canStartRuns: boolean;
  /** Owners manage members and settings; lab admins manage every project. */
  canManage: boolean;
};

export function projectPermissions(
  user: Pick<SessionUser, "role">,
  role: ProjectRole | null | undefined,
): ProjectPermissions {
  const isAdmin = user.role === "admin";
  return {
    canStartRuns: isAdmin || role === "owner" || role === "researcher",
    canManage: isAdmin || role === "owner",
  };
}

/** Only lab admins create projects (the API answers 403 `permission.denied` to anyone else). */
export function canCreateProjects(user: Pick<SessionUser, "role">): boolean {
  return user.role === "admin";
}

/**
 * Whether the user may approve, request changes, reject, cancel or retry a run: lab admins, the
 * project's owners, and researchers on their own runs (the API's `can_steer`).
 */
export function canSteerRun(
  user: Pick<SessionUser, "id" | "role">,
  role: ProjectRole | null | undefined,
  run: Pick<RunOut, "owner_id">,
): boolean {
  return (
    user.role === "admin" || role === "owner" || (role === "researcher" && run.owner_id === user.id)
  );
}

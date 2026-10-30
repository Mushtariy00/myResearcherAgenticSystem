import type { ProjectRole } from "@/client";
import type { SessionUser } from "@/lib/session-user";

export type ProjectPermissions = {
  /** Owners and researchers start runs (lab admins too). */
  canStartRuns: boolean;
  /** Owners add people, change roles and remove members (lab admins too). */
  canManageMembers: boolean;
  /** Owners and lab admins save the project settings; everyone else reads them. */
  canEditSettings: boolean;
};

/**
 * What the signed-in user may do in a project, the same rules as Classic and the API
 * (docs/PLAN.md): lab admins may do everything; otherwise it depends on the project role.
 * The API checks again, so a stale role can at worst show a control that then answers
 * `permission.denied`.
 */
export function projectPermissions(
  userRole: SessionUser["role"],
  projectRole: ProjectRole | null | undefined,
): ProjectPermissions {
  const admin = userRole === "admin";
  const owner = projectRole === "owner";
  return {
    canStartRuns: admin || owner || projectRole === "researcher",
    canManageMembers: admin || owner,
    canEditSettings: admin || owner,
  };
}

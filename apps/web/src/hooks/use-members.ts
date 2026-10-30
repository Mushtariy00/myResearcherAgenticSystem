"use client";

import {
  type QueryClient,
  type UseQueryResult,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import type { ListMembersError, MemberOut, ProjectRole } from "@/client";
import {
  addMemberMutation,
  getProjectQueryKey,
  listMembersOptions,
  listMembersQueryKey,
  listProjectsQueryKey,
  removeMemberMutation,
  updateMemberMutation,
} from "@/client/@tanstack/react-query.gen";
import { ApiError, toApiError } from "@/lib/api-error";

/**
 * What an action of the shared hooks resolves to. Actions never reject, so event handlers need
 * no try/catch: check `ok`, and show `error` (an ApiError; translate it with useErrorMessage).
 */
export type ActionResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

export const MEMBER_ROLES = [
  "owner",
  "researcher",
  "viewer",
] as const satisfies readonly ProjectRole[];

export type MemberAction = "add" | "updateRole" | "remove";

export type MemberActionError = {
  action: MemberAction;
  /**
   * The member acted on. When adding: null, or the member who already has that email
   * (`exists`) once the list shows them.
   */
  userId: string | null;
  /** `code` is e.g. "member.last_owner", "member.not_found", "user.not_found", "permission.denied". */
  error: ApiError;
  /** "member.last_owner": the project must keep at least one owner. */
  lastOwner: boolean;
  /**
   * "member.not_found" (someone removed them meanwhile; the list has been refreshed) or
   * "user.not_found" (no account has that email: a lab admin has to invite them first).
   */
  notFound: boolean;
  /** "member.exists": that person is in the project already; their role changes in the list. */
  exists: boolean;
  /** The email an add was for. */
  email?: string;
};

export type ProjectMembers = {
  /** The member list query (TanStack). */
  query: UseQueryResult<MemberOut[], ListMembersError>;
  /** Members in the order they joined; [] until loaded. */
  members: MemberOut[];
  /**
   * Adds someone by the email they were invited with. A member already in the project is
   * refused (409 `member.exists`): roles change through `updateRole`, which guards the owners.
   */
  add: (input: { email: string; role: ProjectRole }) => Promise<ActionResult<MemberOut>>;
  updateRole: (userId: string, role: ProjectRole) => Promise<ActionResult<MemberOut>>;
  remove: (userId: string) => Promise<ActionResult<null>>;
  isAdding: boolean;
  /** Members with a role change or removal on its way (disable their controls). */
  pendingUserIds: ReadonlySet<string>;
  /** The last action that failed; cleared when the next action starts. */
  lastError: MemberActionError | null;
  clearError: () => void;
};

const EMAIL = /^[^@\s]+@[^@\s]+$/;

/** The API's check of a member email (one @, no spaces, at most 320 characters). */
export function isMemberEmail(email: string): boolean {
  const value = email.trim();
  return value.length <= 320 && EMAIL.test(value);
}

function upsert(list: MemberOut[] | undefined, member: MemberOut): MemberOut[] | undefined {
  if (!list) {
    return list;
  }
  return list.some((item) => item.user_id === member.user_id)
    ? list.map((item) => (item.user_id === member.user_id ? member : item))
    : [...list, member];
}

/** Members, the project (`my_role`) and the project list may all change with a membership. */
function refreshMembership(queryClient: QueryClient, projectId: string): void {
  const path = { project_id: projectId };
  void queryClient.invalidateQueries({ queryKey: listMembersQueryKey({ path }) });
  void queryClient.invalidateQueries({ queryKey: getProjectQueryKey({ path }) });
  void queryClient.invalidateQueries({ queryKey: listProjectsQueryKey() });
}

/**
 * A project's members, and (for owners and lab admins) adding people, changing roles and
 * removing members. Changes wait for the API (no optimistic update: a refused change, such as
 * demoting the last owner, must never look done), then update the list at once and refresh it.
 */
export function useMembers(projectId: string): ProjectMembers {
  const queryClient = useQueryClient();
  const query = useQuery({
    ...listMembersOptions({ path: { project_id: projectId } }),
    staleTime: 30_000,
  });
  const [pendingUserIds, setPendingUserIds] = useState<ReadonlySet<string>>(() => new Set());
  const [lastError, setLastError] = useState<MemberActionError | null>(null);
  const addMember = useMutation(addMemberMutation());
  const updateMember = useMutation(updateMemberMutation());
  const removeMember = useMutation(removeMemberMutation());

  const perform = useCallback(
    async <T>(
      action: MemberAction,
      userId: string | null,
      request: () => Promise<T>,
      update: (list: MemberOut[] | undefined, data: T) => MemberOut[] | undefined,
    ): Promise<ActionResult<T>> => {
      setLastError(null);
      const mark = (busy: boolean) => {
        if (userId === null) {
          return;
        }
        setPendingUserIds((current) => {
          const next = new Set(current);
          if (busy) {
            next.add(userId);
          } else {
            next.delete(userId);
          }
          return next;
        });
      };
      mark(true);
      try {
        const data = await request();
        queryClient.setQueryData(
          listMembersQueryKey({ path: { project_id: projectId } }),
          (list: MemberOut[] | undefined) => update(list, data),
        );
        refreshMembership(queryClient, projectId);
        return { ok: true, data };
      } catch (cause) {
        const error = toApiError(cause);
        setLastError({
          action,
          userId,
          error,
          lastOwner: error.code === "member.last_owner",
          notFound: error.code === "member.not_found" || error.code === "user.not_found",
          exists: error.code === "member.exists",
        });
        if (error.code === "member.not_found") {
          refreshMembership(queryClient, projectId);
        }
        return { ok: false, error };
      } finally {
        mark(false);
      }
    },
    [projectId, queryClient],
  );

  const add = useCallback(
    async ({ email, role }: { email: string; role: ProjectRole }) => {
      if (!isMemberEmail(email)) {
        const error = new ApiError("validation.failed", 422);
        setLastError({
          action: "add",
          userId: null,
          error,
          lastOwner: false,
          notFound: false,
          exists: false,
        });
        return { ok: false, error } satisfies ActionResult<MemberOut>;
      }
      const result = await perform(
        "add",
        null,
        () =>
          addMember.mutateAsync({
            path: { project_id: projectId },
            body: { email: email.trim(), role },
          }),
        upsert,
      );
      if (!result.ok && result.error.code === "member.exists") {
        // Remember whom it was about (to point at their role control), and refresh the list
        // in case they joined after it loaded.
        const existingEmail = email.trim();
        setLastError((current) =>
          current?.action === "add" ? { ...current, email: existingEmail } : current,
        );
        refreshMembership(queryClient, projectId);
      }
      return result;
    },
    [addMember.mutateAsync, perform, projectId, queryClient],
  );

  const updateRole = useCallback(
    (userId: string, role: ProjectRole) =>
      perform(
        "updateRole",
        userId,
        () =>
          updateMember.mutateAsync({
            path: { project_id: projectId, user_id: userId },
            body: { role },
          }),
        upsert,
      ),
    [perform, projectId, updateMember.mutateAsync],
  );

  const remove = useCallback(
    (userId: string) =>
      perform(
        "remove",
        userId,
        async () => {
          await removeMember.mutateAsync({ path: { project_id: projectId, user_id: userId } });
          return null;
        },
        (list) => list?.filter((member) => member.user_id !== userId),
      ),
    [perform, projectId, removeMember.mutateAsync],
  );

  const clearError = useCallback(() => setLastError(null), []);

  // An add refused with `member.exists` names the member as soon as the list shows them.
  const resolvedError = useMemo(() => {
    const email = lastError?.exists && lastError.userId === null ? lastError.email : undefined;
    const member = email
      ? query.data?.find((item) => item.email.toLowerCase() === email.toLowerCase())
      : undefined;
    return member && lastError ? { ...lastError, userId: member.user_id } : lastError;
  }, [lastError, query.data]);

  return {
    query,
    members: query.data ?? [],
    add,
    updateRole,
    remove,
    isAdding: addMember.isPending,
    pendingUserIds,
    lastError: resolvedError,
    clearError,
  };
}

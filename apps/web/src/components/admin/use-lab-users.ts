"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { authClient } from "@/lib/auth-client";

export const ADMIN_USERS_QUERY_KEY = ["admin", "users"] as const;

/** A lab account as the Better Auth admin plugin lists it. */
export type LabUser = {
  id: string;
  name: string;
  email: string;
  role?: string | null | undefined;
  banned?: boolean | null | undefined;
  createdAt: Date | string;
};

/** A failed Better Auth call, keeping the code and status to translate it. */
export class AuthRequestError extends Error {
  readonly code: string | undefined;
  readonly status: number | undefined;
  constructor(error: { code?: string | undefined; status?: number | undefined }) {
    super(error.code ?? "UNKNOWN");
    this.code = error.code;
    this.status = error.status;
  }
}

/** The `{ code, status }` of a failed Better Auth call, for `authErrorKey`. */
export function authErrorOf(
  error: unknown,
): { code: string | undefined; status: number | undefined } | null {
  return error instanceof AuthRequestError ? { code: error.code, status: error.status } : null;
}

/**
 * Every account of the lab, newest first (lab admins only), for the users and budgets tables of
 * both interfaces and to name the people in the audit log.
 */
export function useLabUsers(): UseQueryResult<LabUser[], Error> {
  return useQuery({
    queryKey: ADMIN_USERS_QUERY_KEY,
    queryFn: async (): Promise<LabUser[]> => {
      const { data, error } = await authClient.admin.listUsers({
        query: { limit: 500, sortBy: "createdAt", sortDirection: "desc" },
      });
      if (error) {
        throw new AuthRequestError(error);
      }
      return data.users as LabUser[];
    },
  });
}

/** The name to show for an account: its name, else its email. */
export function displayName(user: Pick<LabUser, "name" | "email">): string {
  return user.name.trim() || user.email;
}

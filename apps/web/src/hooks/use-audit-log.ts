"use client";

import { keepPreviousData, type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { AuditEntryOut, AuditPage, ListAuditLogData, ListAuditLogError } from "@/client";
import { listAuditLogOptions } from "@/client/@tanstack/react-query.gen";

/** Actions the API records today, for a filter menu (the filter takes any action). */
export const AUDIT_ACTIONS = [
  "project.create",
  "project.settings",
  "project.member_set",
  "project.member_remove",
  "run.cancel",
  "run.retry",
  "stage.approve",
  "stage.request_changes",
  "stage.reject",
  "budget.set",
  "settings.paid_models",
] as const;

export const AUDIT_PAGE_SIZE = { default: 50, max: 200 } as const;

export type AuditLog = {
  /** The page query (TanStack); while another page loads it keeps the previous one. */
  query: UseQueryResult<AuditPage, ListAuditLogError>;
  /** Entries of the page, newest first; [] until the first page arrives. */
  items: AuditEntryOut[];
  /** Entries matching the filter, over every page. */
  total: number;
  pageIndex: number;
  pageSize: number;
  /** At least 1. */
  pageCount: number;
  hasPreviousPage: boolean;
  hasNextPage: boolean;
};

/**
 * Admin: one page of the audit log (0-based `pageIndex`), newest first, optionally only one
 * `action` (e.g. "run.cancel"). The caller owns the page: reset it to 0 when the filter changes.
 * Lab admins only (403 otherwise).
 */
export function useAuditLog(
  pageIndex = 0,
  action?: string | null,
  pageSize: number = AUDIT_PAGE_SIZE.default,
): AuditLog {
  const size = Number.isFinite(pageSize)
    ? Math.min(AUDIT_PAGE_SIZE.max, Math.max(1, Math.floor(pageSize)))
    : AUDIT_PAGE_SIZE.default;
  const page = Number.isFinite(pageIndex) ? Math.max(0, Math.floor(pageIndex)) : 0;
  const filter = action?.trim().slice(0, 64);
  const params: NonNullable<ListAuditLogData["query"]> = { limit: size, offset: page * size };
  if (filter) {
    params.action = filter;
  }
  const query = useQuery({
    ...listAuditLogOptions({ query: params }),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / size));
  return {
    query,
    items: query.data?.items ?? [],
    total,
    pageIndex: page,
    pageSize: size,
    pageCount,
    hasPreviousPage: page > 0,
    hasNextPage: page + 1 < pageCount,
  };
}

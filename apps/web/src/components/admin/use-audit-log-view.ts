"use client";

import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";
import { AUDIT_ACTIONS, useAuditLog } from "@/hooks/use-audit-log";
import { useAdminLabels } from "./admin-labels";
import { displayName, useLabUsers } from "./use-lab-users";

/** The page size of the audit tables (the API allows up to 200). */
export const AUDIT_TABLE_PAGE_SIZE = 25;

/** The action filter's value for "every action". */
export const ALL_ACTIONS = "all";

/** The options of the action filter: every action, or one recorded action (translated). */
export function useAuditActionItems(): Record<string, string> {
  const t = useTranslations("admin.audit");
  const labels = useAdminLabels();
  return {
    [ALL_ACTIONS]: t("allActions"),
    ...Object.fromEntries(AUDIT_ACTIONS.map((action) => [action, labels.auditAction(action)])),
  };
}

/**
 * State of the audit tables of both interfaces: the page, the action filter (back to the first
 * page when it changes), which entries are expanded, and names for the people they mention.
 */
export function useAuditLogView() {
  const [page, setPage] = useState(0);
  const [action, setAction] = useState<string>(ALL_ACTIONS);
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());
  const log = useAuditLog(page, action === ALL_ACTIONS ? null : action, AUDIT_TABLE_PAGE_SIZE);
  const users = useLabUsers();

  const names = useMemo(
    () => new Map((users.data ?? []).map((user) => [user.id, displayName(user)])),
    [users.data],
  );
  const userName = useCallback((id: string) => names.get(id) ?? null, [names]);

  const filter = useCallback((value: unknown) => {
    const next =
      typeof value === "string" && (AUDIT_ACTIONS as readonly string[]).includes(value)
        ? value
        : ALL_ACTIONS;
    setAction(next);
    setPage(0);
    setExpanded(new Set());
  }, []);

  const toggle = useCallback((id: number) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const goTo = useCallback((next: number) => {
    setPage(Math.max(0, next));
    setExpanded(new Set());
  }, []);

  const from = log.total === 0 ? 0 : log.pageIndex * log.pageSize + 1;
  const to = Math.min(log.total, log.pageIndex * log.pageSize + log.items.length);

  return {
    log,
    action,
    filter,
    expanded,
    toggle,
    page: log.pageIndex,
    goTo,
    from,
    to,
    userName,
    filtered: action !== ALL_ACTIONS,
  };
}

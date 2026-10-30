"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useMemo } from "react";
import type { AuditEntryOut, HealthCheckOut, RoleRoutingOut, RoutedModelOut } from "@/client";
import { AUDIT_ACTIONS } from "@/hooks/use-audit-log";
import { isKnownStage } from "@/lib/labels";
import type { InterfacePrefix } from "@/lib/notifications";
import { COMPACT, modelPricing, monthDate, PRICE } from "./admin-format";

/**
 * Names for the codes the admin endpoints return (health details, audit actions, services,
 * agent roles), shared by Classic and Studio. Unknown codes are shown as they are, so a newer
 * API never breaks the page.
 */

/** Detail codes of GET /api/v1/admin/health (apps/api/src/agentic_api/health.py). */
export const HEALTH_DETAIL_CODES = [
  "health.timeout",
  "health.unreachable",
  "health.bad_status",
  "health.slow",
  "health.no_pollers",
  "health.partial_pollers",
  "health.unconfigured",
  "health.unsupported",
  "db.unavailable",
] as const;

export type HealthDetailCode = (typeof HEALTH_DETAIL_CODES)[number];

export function isHealthDetailCode(value: string | null | undefined): value is HealthDetailCode {
  return typeof value === "string" && (HEALTH_DETAIL_CODES as readonly string[]).includes(value);
}

/** Every action the API records in the audit log (apps/api/src/agentic_api/routers). */
export type AuditAction = (typeof AUDIT_ACTIONS)[number];

export function isAuditAction(value: string): value is AuditAction {
  return (AUDIT_ACTIONS as readonly string[]).includes(value);
}

export type HealthService = HealthCheckOut["name"];
export type HealthStatus = HealthCheckOut["status"];
export type AgentRole = RoleRoutingOut["role"];

const SERVICES: readonly string[] = [
  "postgres",
  "valkey",
  "temporal",
  "gateway",
  "worker",
] satisfies readonly HealthService[];

const STATUSES: readonly string[] = [
  "ok",
  "degraded",
  "down",
  "unknown",
] satisfies readonly HealthStatus[];

const AGENT_ROLES: readonly string[] = [
  "researcher",
  "screener",
  "analyst",
  "methodologist",
  "coder",
  "writer",
] satisfies readonly AgentRole[];

const TARGET_TYPES = ["project", "run", "stage_output", "user", "setting"] as const;

type TargetType = (typeof TARGET_TYPES)[number];

function isTargetType(value: string): value is TargetType {
  return (TARGET_TYPES as readonly string[]).includes(value);
}

/** The tone of a health status, shared with the status pills of both interfaces. */
export const HEALTH_TONES: Record<HealthStatus, "success" | "warning" | "danger" | "neutral"> = {
  ok: "success",
  degraded: "warning",
  down: "danger",
  unknown: "neutral",
};

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Where an audit entry's target lives in the interface with `prefix`, if it has a page. */
export function auditTargetHref(entry: AuditEntryOut, prefix: InterfacePrefix): string | null {
  switch (entry.target_type) {
    case "project":
      return `${prefix}/projects/${encodeURIComponent(entry.target_id)}`;
    case "run":
      return `${prefix}/runs/${encodeURIComponent(entry.target_id)}`;
    case "stage_output": {
      const runId = text(entry.details.run_id);
      return runId ? `${prefix}/runs/${encodeURIComponent(runId)}` : null;
    }
    default:
      return null;
  }
}

/** What the expanded row of an audit entry shows: its full target and the recorded details. */
export function auditEntryDetails(entry: AuditEntryOut): Record<string, unknown> {
  return { target: { type: entry.target_type, id: entry.target_id }, details: entry.details };
}

/** A long id shortened for a table cell (the full id stays in the details). */
export function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

/** Translated names for the admin codes; anything unknown is returned as it is. */
export function useAdminLabels() {
  const t = useTranslations("admin");
  const tStages = useTranslations("stages");

  const healthDetail = useCallback(
    (code: string | null | undefined) =>
      isHealthDetailCode(code) ? t(`health.details.${code}`) : (code ?? null),
    [t],
  );
  const service = useCallback(
    (name: string) =>
      SERVICES.includes(name) ? t(`health.services.${name as HealthService}`) : name,
    [t],
  );
  const healthStatus = useCallback(
    (status: string) =>
      STATUSES.includes(status) ? t(`health.status.${status as HealthStatus}`) : status,
    [t],
  );
  const auditAction = useCallback(
    (action: string) => (isAuditAction(action) ? t(`audit.actions.${action}`) : action),
    [t],
  );
  const agentRole = useCallback(
    (role: string) => (AGENT_ROLES.includes(role) ? t(`routing.roles.${role as AgentRole}`) : role),
    [t],
  );

  /** "Project", "Run", ... with the most telling name the entry carries. */
  const auditTarget = useCallback(
    (entry: AuditEntryOut, userName: (id: string) => string | null) => {
      const type = isTargetType(entry.target_type)
        ? t(`audit.targets.${entry.target_type}`)
        : entry.target_type;
      let name: string | null = null;
      if (entry.target_type === "project") {
        name = text(entry.details.name);
      } else if (entry.target_type === "user") {
        name = userName(entry.target_id);
      } else if (entry.target_type === "stage_output") {
        const stage = text(entry.details.stage);
        name = stage && isKnownStage(stage) ? tStages(stage) : stage;
      } else if (entry.target_type === "setting") {
        name = entry.target_id;
      }
      return { type, name: name ?? shortId(entry.target_id) };
    },
    [t, tStages],
  );

  return useMemo(
    () => ({ healthDetail, service, healthStatus, auditAction, agentRole, auditTarget }),
    [healthDetail, service, healthStatus, auditAction, agentRole, auditTarget],
  );
}

/** A month as "October 2026" in the UI language (the API sends "2026-10"). */
export function useMonthName(): (month: string) => string {
  const format = useFormatter();
  return useCallback(
    (month: string) => {
      const date = monthDate(month);
      return date ? format.dateTime(date, { year: "numeric", month: "long" }) : month;
    },
    [format],
  );
}

/** A routed model's price and context window as short sentences ("$0.30 in · $2.50 out…"). */
export function useModelText(): (model: RoutedModelOut) => {
  price: string;
  context: string | null;
} {
  const t = useTranslations("admin.routing");
  const format = useFormatter();
  return useCallback(
    (model: RoutedModelOut) => {
      const pricing = modelPricing(model);
      const price =
        pricing.kind === "free"
          ? t("freePrice")
          : pricing.kind === "unknown"
            ? t("notInCatalog")
            : t("price", {
                prompt: format.number(pricing.prompt, PRICE),
                completion: format.number(pricing.completion, PRICE),
              });
      const context =
        model.context_length && model.context_length > 0
          ? t("context", { tokens: format.number(model.context_length, COMPACT) })
          : null;
      return { price, context };
    },
    [t, format],
  );
}

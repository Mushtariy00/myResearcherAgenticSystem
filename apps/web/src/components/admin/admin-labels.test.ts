import { describe, expect, it } from "vitest";
import type { AuditEntryOut } from "@/client";
import { AUDIT_ACTIONS } from "@/hooks/use-audit-log";
import { NOTIFICATION_MESSAGE_KEYS } from "@/lib/notifications";
import { enMessages, koMessages } from "@/test/messages";
import { auditTargetHref, HEALTH_DETAIL_CODES, shortId } from "./admin-labels";
import { ADMIN_TABS, parseAdminTab } from "./admin-sections";

type Tree = { [key: string]: string | Tree };

function lookup(tree: Tree, path: string): unknown {
  return path.split(".").reduce<unknown>((node, key) => (node as Tree | undefined)?.[key], tree);
}

function expectTranslated(path: string) {
  expect(typeof lookup(enMessages, path), `en: ${path}`).toBe("string");
  expect(typeof lookup(koMessages, path), `ko: ${path}`).toBe("string");
}

describe("admin translations", () => {
  it("names every health detail code the API sends", () => {
    // apps/api/src/agentic_api/health.py
    const fromApi = [
      "health.timeout",
      "health.unreachable",
      "health.bad_status",
      "health.slow",
      "health.no_pollers",
      "health.partial_pollers",
      "health.unconfigured",
      "health.unsupported",
      "db.unavailable",
    ];
    expect([...HEALTH_DETAIL_CODES].sort()).toEqual(fromApi.sort());
    for (const code of HEALTH_DETAIL_CODES) {
      expectTranslated(`admin.health.details.${code}`);
    }
  });

  it("names every audit action the API records", () => {
    // AuditLog(action=...) in apps/api/src/agentic_api/routers (stage.<decision> from runs.py).
    const fromApi = [
      "budget.set",
      "project.create",
      "project.member_set",
      "project.member_remove",
      "project.settings",
      "run.cancel",
      "run.retry",
      "stage.approve",
      "stage.request_changes",
      "stage.reject",
      "settings.paid_models",
    ];
    expect([...AUDIT_ACTIONS].sort()).toEqual(fromApi.sort());
    for (const action of AUDIT_ACTIONS) {
      expectTranslated(`admin.audit.actions.${action}`);
    }
  });

  it("names the services, statuses, agent roles, audit targets and tabs", () => {
    for (const service of ["postgres", "valkey", "temporal", "gateway", "worker"]) {
      expectTranslated(`admin.health.services.${service}`);
    }
    for (const status of ["ok", "degraded", "down", "unknown"]) {
      expectTranslated(`admin.health.status.${status}`);
    }
    for (const role of ["researcher", "screener", "analyst", "methodologist", "coder", "writer"]) {
      expectTranslated(`admin.routing.roles.${role}`);
    }
    for (const target of ["project", "run", "stage_output", "user", "setting"]) {
      expectTranslated(`admin.audit.targets.${target}`);
    }
    for (const tab of ADMIN_TABS) {
      expectTranslated(`admin.tabs.${tab}`);
    }
  });

  it("has a sentence for every notification message key", () => {
    for (const key of NOTIFICATION_MESSAGE_KEYS) {
      expectTranslated(key);
    }
  });
});

describe("admin helpers", () => {
  const entry = (overrides: Partial<AuditEntryOut>): AuditEntryOut => ({
    id: 1,
    actor_id: "user-1",
    actor_name: "Ada",
    actor_email: "ada@lab.example",
    action: "run.cancel",
    target_type: "run",
    target_id: "run-1",
    details: {},
    created_at: "2026-10-30T01:00:00Z",
    ...overrides,
  });

  it("links audit targets to their page in either interface", () => {
    expect(auditTargetHref(entry({}), "")).toBe("/runs/run-1");
    expect(auditTargetHref(entry({ target_type: "project", target_id: "p/1" }), "/studio")).toBe(
      "/studio/projects/p%2F1",
    );
    expect(
      auditTargetHref(
        entry({ target_type: "stage_output", target_id: "out-1", details: { run_id: "run-9" } }),
        "",
      ),
    ).toBe("/runs/run-9");
    expect(auditTargetHref(entry({ target_type: "stage_output", details: {} }), "")).toBeNull();
    expect(auditTargetHref(entry({ target_type: "user", target_id: "user-2" }), "")).toBeNull();
  });

  it("shortens long ids and reads the tab from the URL", () => {
    expect(shortId("33333333-3333-4333-8333-333333333333")).toBe("33333333…");
    expect(shortId("paid_models")).toBe("paid_models");
    expect(parseAdminTab("health")).toBe("health");
    expect(parseAdminTab(["audit", "health"])).toBe("audit");
    expect(parseAdminTab("nope")).toBe("users");
    expect(parseAdminTab(undefined)).toBe("users");
  });
});

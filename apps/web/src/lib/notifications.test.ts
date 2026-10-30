import { describe, expect, it } from "vitest";
import type { NotificationList, NotificationOut } from "@/client";
import {
  describeNotification,
  interfacePrefix,
  NOTIFICATION_MESSAGE_KEYS,
  notificationHref,
  notificationIcon,
  notificationMessageKey,
  withNotificationsRead,
} from "./notifications";

const RUN = "22222222-2222-4222-8222-222222222222";
const PROJECT = "33333333-3333-4333-8333-333333333333";

function notification(overrides: Partial<NotificationOut>): NotificationOut {
  return {
    key: `run.finished:${RUN}`,
    kind: "run_completed",
    created_at: "2026-10-30T01:00:00Z",
    read: false,
    run_id: RUN,
    project_id: PROJECT,
    stage: null,
    params: { topic: "Monocular depth", project: "Depth lab", error: null },
    ...overrides,
  };
}

describe("describeNotification", () => {
  it("asks for a review of a waiting output, on the run page of each interface", () => {
    const waiting = notification({
      key: "approval:abc",
      kind: "approval_needed",
      stage: "method",
      params: { topic: "Monocular depth", project: "Depth lab", stage: "method" },
    });
    expect(describeNotification(waiting, "")).toEqual({
      messageKey: "notifications.items.approvalNeeded",
      values: { topic: "Monocular depth", project: "Depth lab", stage: "method" },
      icon: "eye",
      tone: "warning",
      href: `/runs/${RUN}`,
      needsAction: true,
    });
    expect(describeNotification(waiting, "/studio").href).toBe(`/studio/runs/${RUN}`);
  });

  it("warns before an approval expires, with the expiry as a date", () => {
    const view = describeNotification(
      notification({
        key: "approval.expiring:abc",
        kind: "approval_expiring",
        stage: "coding",
        params: {
          topic: "Monocular depth",
          project: "Depth lab",
          stage: "coding",
          days: 7,
          expires_at: "2026-11-02T09:00:00+00:00",
        },
      }),
      "",
    );
    expect(view).toMatchObject({
      messageKey: "notifications.items.approvalExpiring",
      icon: "hourglass",
      tone: "danger",
      needsAction: true,
    });
    expect(view.values).toEqual({
      topic: "Monocular depth",
      project: "Depth lab",
      stage: "coding",
      days: 7,
      expiresAt: new Date("2026-11-02T09:00:00Z"),
    });
  });

  it("reports finished runs with their outcome", () => {
    const cases = [
      ["run_completed", "notifications.items.runCompleted", "circle-check", "success"],
      ["run_failed", "notifications.items.runFailed", "triangle-alert", "danger"],
      ["run_cancelled", "notifications.items.runCancelled", "ban", "neutral"],
      ["run_rejected", "notifications.items.runRejected", "circle-x", "danger"],
    ] as const;
    for (const [kind, messageKey, icon, tone] of cases) {
      const view = describeNotification(notification({ kind }), "");
      expect(view, kind).toMatchObject({ messageKey, icon, tone, needsAction: false });
      expect(view.href).toBe(`/runs/${RUN}`);
    }
  });

  it("passes a failed run's error code along for translation", () => {
    const failed = notification({
      kind: "run_failed",
      params: { topic: "Depth", project: "Lab", error: "orchestrator.unavailable" },
    });
    expect(describeNotification(failed, "").values).toEqual({
      topic: "Depth",
      project: "Lab",
      error: "orchestrator.unavailable",
    });
    expect(describeNotification(notification({ kind: "run_completed" }), "").values).toEqual({
      topic: "Monocular depth",
      project: "Depth lab",
    });
  });

  it("tells a budget warning from a used-up budget, and links nowhere", () => {
    const alert = (percent: number) =>
      notification({
        key: `budget:2026-10:${percent}`,
        kind: "budget_alert",
        run_id: null,
        project_id: null,
        params: { percent, month: "2026-10", budget_usd: "20.00", spent_usd: "16.25" },
      });
    expect(describeNotification(alert(80), "/studio")).toEqual({
      messageKey: "notifications.items.budgetWarning",
      values: { percent: 80, month: "2026-10", budget: 20, spent: 16.25 },
      icon: "wallet",
      tone: "warning",
      href: null,
      needsAction: false,
    });
    expect(describeNotification(alert(100), "")).toMatchObject({
      messageKey: "notifications.items.budgetExhausted",
      tone: "danger",
    });
  });

  it("copes with missing parameters and kinds this version does not know", () => {
    const bare = notification({ kind: "approval_needed", stage: "literature", params: {} });
    expect(describeNotification(bare, "").values).toEqual({
      topic: "",
      project: "",
      stage: "literature",
    });
    const future = notification({ kind: "gpu_job_started" as NotificationOut["kind"] });
    expect(describeNotification(future, "")).toMatchObject({
      messageKey: "notifications.items.unknown",
      icon: "bell",
      tone: "neutral",
      values: {},
      href: `/runs/${RUN}`,
    });
  });

  it("uses only the message keys it declares", () => {
    const kinds = [
      "approval_needed",
      "approval_expiring",
      "run_completed",
      "run_failed",
      "run_cancelled",
      "run_rejected",
      "budget_alert",
    ] as const;
    for (const kind of kinds) {
      expect(NOTIFICATION_MESSAGE_KEYS).toContain(notificationMessageKey(notification({ kind })));
      expect(typeof notificationIcon(notification({ kind }))).toBe("string");
    }
  });
});

describe("notificationHref", () => {
  it("prefers the run, then the project, and encodes the ids", () => {
    expect(notificationHref(notification({}), "/studio")).toBe(`/studio/runs/${RUN}`);
    expect(notificationHref(notification({ run_id: null }), "")).toBe(`/projects/${PROJECT}`);
    expect(notificationHref(notification({ run_id: null }), "/studio")).toBe(
      `/studio/projects/${PROJECT}`,
    );
    expect(notificationHref(notification({ run_id: "a/b?c" }), "")).toBe("/runs/a%2Fb%3Fc");
    expect(notificationHref(notification({ run_id: null, project_id: null }), "")).toBeNull();
  });

  it("knows the prefix of each interface", () => {
    expect(interfacePrefix("classic")).toBe("");
    expect(interfacePrefix("studio")).toBe("/studio");
  });
});

describe("withNotificationsRead", () => {
  const list: NotificationList = {
    items: [
      notification({ key: "a" }),
      notification({ key: "b", read: true }),
      notification({ key: "c" }),
    ],
    // Two more unread notifications exist beyond the listed ones.
    unread_count: 4,
  };

  it("marks the given keys read and counts only the ones that changed", () => {
    const next = withNotificationsRead(list, ["a", "b", "unknown"]);
    expect(next.items.map((item) => [item.key, item.read])).toEqual([
      ["a", true],
      ["b", true],
      ["c", false],
    ]);
    expect(next.unread_count).toBe(3);
    expect(list.items[0]?.read).toBe(false);
  });

  it("returns the same list when nothing changes", () => {
    expect(withNotificationsRead(list, ["b"])).toBe(list);
  });

  it("marks everything read, listed or not", () => {
    const next = withNotificationsRead(list, "all");
    expect(next.items.every((item) => item.read)).toBe(true);
    expect(next.unread_count).toBe(0);
  });
});

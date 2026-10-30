// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { NotificationList, NotificationOut } from "@/client";
import { notification, PROJECT_ID, RUN_ID, renderAs } from "@/components/admin/test-utils";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import { installDomFakes } from "@/studio/test/dom";
import { NotificationsBell } from "./notifications-bell";
import { NotificationsView } from "./notifications-view";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const APPROVAL = notification({
  key: "approval:out-1",
  kind: "approval_needed",
  stage: "method",
  params: { topic: "Monocular depth", project: "Depth lab", stage: "method" },
});
const FINISHED = notification({ key: `run.finished:${RUN_ID}` });
const BUDGET = notification({
  key: "budget:2026-10:80",
  kind: "budget_alert",
  run_id: null,
  project_id: null,
  read: true,
  params: { percent: 80, month: "2026-10", budget_usd: "20.00", spent_usd: "16.25" },
});

/** The server's list: marks stick, as they would in the API. */
let items: NotificationOut[];
let marks: unknown[];

function list(): NotificationList {
  return { items, unread_count: items.filter((item) => !item.read).length };
}

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  items = [APPROVAL, FINISHED, BUDGET];
  marks = [];
  mockApi(async (request, path) => {
    if (path === "/api/v1/me/notifications/read") {
      const body = (await request.json()) as { keys?: string[]; all?: boolean };
      marks.push(body);
      items = items.map((item) =>
        body.all || body.keys?.includes(item.key) ? { ...item, read: true } : item,
      );
      return json(200, list());
    }
    if (path === "/api/v1/me/notifications") {
      return json(200, list());
    }
    return json(404, { detail: "unknown" });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function openBell() {
  fireEvent.click(await screen.findByRole("button", { name: "Notifications, 2 unread" }));
  return screen.findByRole("list", { name: "Latest notifications" });
}

describe("the Classic notifications bell", () => {
  it("shows the unread count and the latest notifications, each linking to its run", async () => {
    renderAs(<NotificationsBell />);
    const latest = await openBell();
    const rows = within(latest).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    const review = within(rows[0] as HTMLElement).getByRole("link");
    expect(review.textContent).toBe(
      "Unread: Method for “Monocular depth” is ready for your review.",
    );
    expect(review.getAttribute("href")).toBe(`/runs/${RUN_ID}`);
    expect(within(rows[0] as HTMLElement).getByText("Needs you")).toBeTruthy();
    // Budget alerts lead nowhere, and read ones have nothing left to mark.
    const budget = rows[2] as HTMLElement;
    expect(within(budget).queryByRole("link")).toBeNull();
    expect(budget.textContent).toContain(
      "You have used 80% of your LLM budget for October 2026: $16.25 of $20.00.",
    );
    expect(within(budget).queryByRole("button", { name: "Mark as read" })).toBeNull();
    expect(screen.getByRole("link", { name: "See all notifications" }).getAttribute("href")).toBe(
      "/notifications",
    );
  });

  it("marks one notification read", async () => {
    renderAs(<NotificationsBell />);
    const latest = await openBell();
    const finished = within(latest).getAllByRole("listitem")[1] as HTMLElement;
    fireEvent.click(within(finished).getByRole("button", { name: "Mark as read" }));

    await waitFor(() => expect(marks).toEqual([{ keys: [FINISHED.key] }]));
    expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeTruthy();
    await waitFor(() =>
      expect(within(finished).queryByRole("button", { name: "Mark as read" })).toBeNull(),
    );
  });

  it("marks everything read at once", async () => {
    renderAs(<NotificationsBell />);
    await openBell();
    fireEvent.click(screen.getByRole("button", { name: "Mark all as read" }));

    await waitFor(() => expect(marks).toEqual([{ all: true }]));
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeTruthy();
    expect(screen.queryAllByRole("button", { name: "Mark as read" })).toHaveLength(0);
  });

  it("marks a notification read when it is opened", async () => {
    renderAs(<NotificationsBell />);
    const latest = await openBell();
    // jsdom cannot follow links; the click handlers still run.
    const stay = (event: Event) => event.preventDefault();
    window.addEventListener("click", stay, { capture: true, once: true });
    fireEvent.click(within(latest).getAllByRole("link")[0] as HTMLElement);
    await waitFor(() => expect(marks).toEqual([{ keys: [APPROVAL.key] }]));
    // Opening a notification also closes the popover.
    await waitFor(() =>
      expect(screen.queryByRole("list", { name: "Latest notifications" })).toBeNull(),
    );
  });
});

describe("the Classic notifications page", () => {
  it("filters the unread notifications and marks them read one by one or all at once", async () => {
    items = [
      APPROVAL,
      FINISHED,
      BUDGET,
      notification({ key: "run.finished:other", project_id: PROJECT_ID, read: true }),
    ];
    renderAs(<NotificationsView />);
    const all = await screen.findByRole("list", { name: "Notifications, newest first" });
    expect(within(all).getAllByRole("listitem")).toHaveLength(4);

    fireEvent.click(screen.getByRole("tab", { name: "Unread (2)" }));
    const unread = await screen.findByRole("list", { name: "Notifications, newest first" });
    expect(within(unread).getAllByRole("listitem")).toHaveLength(2);

    const first = within(unread).getAllByRole("listitem")[0] as HTMLElement;
    fireEvent.click(within(first).getByRole("button", { name: "Mark as read" }));
    await waitFor(() => expect(marks).toEqual([{ keys: [APPROVAL.key] }]));
    await waitFor(() =>
      expect(
        within(screen.getByRole("list", { name: "Notifications, newest first" })).getAllByRole(
          "listitem",
        ),
      ).toHaveLength(1),
    );

    fireEvent.click(screen.getByRole("button", { name: "Mark all as read" }));
    await waitFor(() => expect(marks).toEqual([{ keys: [APPROVAL.key] }, { all: true }]));
    expect(await screen.findByText("Nothing unread")).toBeTruthy();
  });

  it("explains an empty list", async () => {
    items = [];
    renderAs(<NotificationsView />);
    expect(await screen.findByText("You're all caught up")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Mark all as read" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});

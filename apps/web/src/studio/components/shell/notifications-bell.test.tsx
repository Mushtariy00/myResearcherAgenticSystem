// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { NotificationList, NotificationOut } from "@/client";
import { makeQueryClient, notification, RUN_ID, renderAs } from "@/components/admin/test-utils";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import { installDomFakes, setReducedMotion } from "@/studio/test/dom";
import { NotificationsBell } from "./notifications-bell";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let items: NotificationOut[];
let marks: unknown[];

function list(): NotificationList {
  return { items, unread_count: items.filter((item) => !item.read).length };
}

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  items = [
    notification({ key: "approval:out-1", kind: "approval_needed", stage: "coding" }),
    notification({ key: `run.finished:${RUN_ID}` }),
  ];
  marks = [];
  mockApi(async (request, path) => {
    if (path === "/api/v1/me/notifications/read") {
      const body = (await request.json()) as { keys?: string[]; all?: boolean };
      marks.push(body);
      items = items.map((item) =>
        body.all || body.keys?.includes(item.key) ? { ...item, read: true } : item,
      );
    }
    return json(200, list());
  });
});

afterEach(() => {
  cleanup();
  act(() => setReducedMotion(false));
});

const badge = () => document.querySelector<HTMLElement>("[data-slot=unread-badge]");

describe("the Studio notifications bell", () => {
  it("counts unread notifications from useNotifications", async () => {
    const queryClient = makeQueryClient();
    renderAs(<NotificationsBell />, { queryClient });
    expect(await screen.findByRole("button", { name: "Notifications, 2 unread" })).toBeTruthy();
    expect(badge()?.textContent).toBe("2");
  });

  it("pops the badge in, but only fades it with reduced motion", async () => {
    const view = renderAs(<NotificationsBell />);
    await screen.findByRole("button", { name: "Notifications, 2 unread" });
    expect(badge()?.className).toMatch(/\bzoom-in-50\b/);

    act(() => setReducedMotion(true));
    expect(badge()?.className).not.toMatch(/zoom-in/);
    expect(badge()?.className).toMatch(/\bfade-in-0\b/);
    view.unmount();
  });

  it("lists the latest notifications with Studio links and marks them all read", async () => {
    const queryClient = makeQueryClient();
    renderAs(<NotificationsBell />, { queryClient });
    fireEvent.click(await screen.findByRole("button", { name: "Notifications, 2 unread" }));
    const latest = await screen.findByRole("list", { name: "Latest notifications" });
    const links = within(latest).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      `/studio/runs/${RUN_ID}`,
      `/studio/runs/${RUN_ID}`,
    ]);
    expect(links[0]?.textContent).toContain(
      "Coding for “Monocular depth” is ready for your review.",
    );
    expect(screen.getByRole("link", { name: "See all notifications" }).getAttribute("href")).toBe(
      "/studio/notifications",
    );

    fireEvent.click(screen.getByRole("button", { name: "Mark all as read" }));
    await waitFor(() => expect(marks).toEqual([{ all: true }]));
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeTruthy();
    await waitFor(() => expect(badge()).toBeNull());
  });
});

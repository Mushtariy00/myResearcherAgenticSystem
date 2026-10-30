// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { isValidElement } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AppHeader } from "@/components/app/app-header";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import type { SessionUser } from "@/lib/session-user";
import { StudioAdminView } from "@/studio/components/admin/studio-admin-view";
import { installDomFakes } from "@/studio/test/dom";
import { AdminView } from "./admin-view";
import { LAB_ADMIN, MEMBER, renderAs } from "./test-utils";

const session = vi.hoisted(() => ({
  current: null as { user: { id: string; role: string } } | null,
}));
vi.mock("@/lib/session", () => ({ getSession: vi.fn(async () => session.current) }));
vi.mock("next-intl/server", () => ({ getTranslations: vi.fn(async () => (key: string) => key) }));

const NOT_FOUND = "NEXT_NOT_FOUND";
const navigation = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));

// Server actions and Better Auth: none of them may run here.
vi.mock("@/lib/admin-actions", () => ({ inviteUser: vi.fn(), sendPasswordLink: vi.fn() }));
vi.mock("@/lib/admin-offboarding", () => ({
  suspendUser: vi.fn(),
  restoreUser: vi.fn(),
  signOutEverywhere: vi.fn(),
}));
vi.mock("@/i18n/actions", () => ({ setLocale: vi.fn(async () => {}) }));
vi.mock("@/lib/auth-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth-client")>()),
  authClient: {
    admin: { listUsers: vi.fn(async () => ({ data: { users: [] }, error: null })) },
    signOut: vi.fn(async () => ({ error: null })),
  },
}));

const TAB_NAMES = [
  "Users and invites",
  "Budgets",
  "Model routing",
  "Lab balance",
  "System health",
  "Audit log",
];

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  mockApi((_request, path) =>
    path === "/api/v1/admin/health"
      ? json(200, { status: "ok", checked_at: new Date().toISOString(), checks: [] })
      : json(200, { items: [], unread_count: 0 }),
  );
});

afterEach(() => {
  cleanup();
  session.current = null;
});

function tabNames(): string[] {
  return within(screen.getByRole("tablist", { name: "Administration sections" }))
    .getAllByRole("tab")
    .map((tab) => tab.textContent ?? "");
}

describe("the admin page in Classic", () => {
  it("shows every section to a lab admin, opening the one in the URL", () => {
    renderAs(<AdminView initialTab="health" />, { user: LAB_ADMIN });
    expect(tabNames()).toEqual(TAB_NAMES);
    expect(screen.getByRole("tab", { name: "System health" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("renders nothing for anyone else", () => {
    const { container } = renderAs(<AdminView initialTab="users" />, { user: MEMBER });
    expect(container.textContent).toBe("");
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  it("is not found for members, and opens the asked tab for admins", async () => {
    const { default: AdminPage } = await import("@/app/(app)/admin/page");
    const searchParams = Promise.resolve({ tab: "audit" });

    session.current = { user: { id: MEMBER.id, role: "user" } };
    await expect(AdminPage({ searchParams })).rejects.toThrow(NOT_FOUND);
    session.current = null;
    await expect(AdminPage({ searchParams })).rejects.toThrow(NOT_FOUND);

    session.current = { user: { id: LAB_ADMIN.id, role: "admin" } };
    const page = await AdminPage({ searchParams });
    expect(isValidElement(page) && page.type).toBe(AdminView);
    expect((page as { props: { initialTab: string } }).props.initialTab).toBe("audit");
  });
});

describe("the admin page in Studio", () => {
  it("shows every section to a lab admin and nothing to anyone else", () => {
    const view = renderAs(<StudioAdminView initialTab="users" />, { user: LAB_ADMIN });
    expect(tabNames()).toEqual(TAB_NAMES);
    view.unmount();

    const { container } = renderAs(<StudioAdminView initialTab="users" />, { user: MEMBER });
    expect(container.textContent).toBe("");
  });

  it("is not found for members", async () => {
    const { default: StudioAdminPage } = await import("@/app/studio/(app)/admin/page");
    const searchParams = Promise.resolve({});
    session.current = { user: { id: MEMBER.id, role: "user" } };
    await expect(StudioAdminPage({ searchParams })).rejects.toThrow(NOT_FOUND);

    session.current = { user: { id: LAB_ADMIN.id, role: "admin" } };
    const page = await StudioAdminPage({ searchParams });
    expect(isValidElement(page) && page.type).toBe(StudioAdminView);
  });
});

describe("the Classic header", () => {
  function navLinks(user: SessionUser): string[] {
    renderAs(<AppHeader />, { user });
    return within(screen.getByRole("navigation", { name: "Main" }))
      .getAllByRole("link")
      .map((link) => link.textContent ?? "");
  }

  it("links to the admin page for lab admins only", () => {
    expect(navLinks(LAB_ADMIN)).toEqual(["Dashboard", "Papers", "Admin"]);
    cleanup();
    expect(navLinks(MEMBER)).toEqual(["Dashboard", "Papers"]);
  });

  it("has the notifications bell and a profile entry in the account menu", async () => {
    renderAs(<AppHeader />, { user: MEMBER });
    expect(screen.getByRole("button", { name: "Notifications" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Account menu" }));
    const profile = await screen.findByRole("menuitem", { name: "Profile" });
    expect(profile.getAttribute("href")).toBe("/profile");
  });
});

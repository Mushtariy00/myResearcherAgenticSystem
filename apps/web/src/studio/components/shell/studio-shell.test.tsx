// @vitest-environment jsdom
import { cleanup, fireEvent, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { listProjectsQueryKey } from "@/client/@tanstack/react-query.gen";
import { unreadNotificationsQueryKey } from "@/studio/hooks/use-unread-notifications";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { StudioShell } from "./studio-shell";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/studio/dashboard",
}));
vi.mock("@/i18n/actions", () => ({ setLocale: vi.fn(async () => {}) }));
vi.mock("@/lib/auth-client", () => ({ authClient: { signOut: vi.fn(async () => ({})) } }));

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

function renderShell() {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(listProjectsQueryKey(), []);
  queryClient.setQueryData(unreadNotificationsQueryKey, 3);
  renderStudio(
    <StudioShell>
      <p>Page content</p>
    </StudioShell>,
    { user: TEST_USER, queryClient },
  );
  const shell = document.getElementById("studio-shell") as HTMLElement;
  const sidebar = document.getElementById("studio-sidebar") as HTMLElement;
  return { shell, sidebar };
}

describe("StudioShell sidebar", () => {
  it("collapses and expands at once, and fades the labels in only after a toggle", () => {
    const { shell, sidebar } = renderShell();
    expect(shell.getAttribute("data-sidebar")).toBe("expanded");
    // No width transition: it would reflow the whole page on every frame.
    expect(sidebar.className).not.toMatch(/transition/);
    // Nothing to fade on the first paint.
    expect(shell.hasAttribute("data-sidebar-motion")).toBe(false);

    fireEvent.click(within(sidebar).getByRole("button", { name: "Collapse sidebar" }));
    expect(shell.getAttribute("data-sidebar")).toBe("collapsed");
    expect(shell.hasAttribute("data-sidebar-motion")).toBe(true);
    expect(window.localStorage.getItem("studio.sidebar")).toBe("collapsed");

    const expand = within(sidebar).getByRole("button", { name: "Expand sidebar" });
    expect(expand.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(expand);
    expect(shell.getAttribute("data-sidebar")).toBe("expanded");
  });

  it("marks the labels that fade back in, and keeps them for screen readers when collapsed", () => {
    const { sidebar } = renderShell();
    const nav = within(sidebar).getByRole("navigation", { name: "Main" });
    const dashboard = within(nav).getByRole("link", { name: "Dashboard" });
    expect(dashboard.getAttribute("aria-current")).toBe("page");
    expect(dashboard.querySelector(".studio-sidebar-label")?.textContent).toBe("Dashboard");
    expect(within(nav).getByRole("link", { name: /Notifications/ }).textContent).toMatch(/3/);
  });
});

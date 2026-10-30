// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  listNotificationsQueryKey,
  listProjectsQueryKey,
} from "@/client/@tanstack/react-query.gen";
import { NonceContext } from "@/components/nonce";
import { InlineScript } from "@/studio/components/inline-script";
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
  // The shared notifications query (useNotifications), as the bell and the sidebar read it.
  queryClient.setQueryData(listNotificationsQueryKey(), { items: [], unread_count: 3 });
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

  it("sets the brand row level with the top bar's row", () => {
    const { shell, sidebar } = renderShell();
    const brand = within(sidebar).getByRole("link", { name: /Agentic Research Platform/ });
    const row = brand.parentElement as HTMLElement;
    const topBarRow = shell.querySelector("header > div") as HTMLElement;
    // Same height (h-14), and no padding above the row in the sidebar.
    expect(row.className).toMatch(/(^|\s)h-14(\s|$)/);
    expect(topBarRow.className).toMatch(/(^|\s)h-14(\s|$)/);
    expect(sidebar.className).not.toMatch(/(^|\s)(py|pt)-\d/);
  });
});

describe("StudioShell user card", () => {
  it("is named by the visible name and role, also when the sidebar is collapsed", () => {
    const { sidebar } = renderShell();
    // The visible name leads the accessible name (no aria-label replacing it).
    const card = within(sidebar).getByRole("button", { name: /^Ada Lovelace\s*Member$/ });
    expect(card.hasAttribute("aria-label")).toBe(false);
    expect(card.getAttribute("aria-haspopup")).toBe("menu");

    fireEvent.click(within(sidebar).getByRole("button", { name: "Collapse sidebar" }));
    const collapsed = within(sidebar).getByRole("button", { name: /^Ada Lovelace\s*Member$/ });
    // The words stay for screen readers (sr-only), never display: none.
    expect(collapsed.querySelector(".studio-sidebar-label")?.className).toMatch(/:sr-only/);
    expect(collapsed.querySelector(".studio-sidebar-label")?.className).not.toMatch(/:hidden/);
    expect(collapsed.getAttribute("title")).toBe("Ada Lovelace (Member)");
  });

  it("opens the profile from its menu", async () => {
    const { sidebar } = renderShell();
    fireEvent.click(within(sidebar).getByRole("button", { name: /^Ada Lovelace/ }));
    const profile = await screen.findByRole("menuitem", { name: "Profile" });
    expect(profile.getAttribute("href")).toBe("/studio/profile");
    expect(screen.getByRole("menuitem", { name: "Open in Classic" }).getAttribute("href")).toBe(
      "/",
    );
  });
});

describe("InlineScript", () => {
  it("renders an inert data block on the client, which React does not warn about", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    renderShell();
    const script = document.querySelector("#studio-shell > script") as HTMLScriptElement;
    expect(script.type).toBe("text/plain");
    expect(errors.mock.calls.flat().join(" ")).not.toMatch(/Encountered a script tag/);
    errors.mockRestore();
  });

  it("carries the page's CSP nonce, without which the browser would not run it", () => {
    render(
      <NonceContext value="page-nonce">
        <InlineScript html="window.ran = true" />
      </NonceContext>,
    );
    expect(document.querySelector("script")?.getAttribute("nonce")).toBe("page-nonce");
  });
});

// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { isValidElement, type ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import StudioAppLayout from "@/app/studio/(app)/layout";
import { CurrentUserProvider } from "@/components/app/current-user";
import { getSession } from "@/lib/session";
import { StudioLoginRedirect } from "./studio-login-redirect";

const navigation = vi.hoisted(() => ({
  pathname: "/studio/papers",
  search: "q=depth",
  redirect: vi.fn((url: string): never => {
    throw new Error(`NEXT_REDIRECT ${url}`);
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => navigation.redirect(url),
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

vi.mock("@/lib/session", () => ({ getSession: vi.fn() }));

vi.mock("@/studio/components/shell/studio-shell", () => ({
  StudioShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="studio-shell">{children}</div>
  ),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** Runs the redirect component the layout rendered (it throws, as next/navigation does). */
function runRedirect(element: ReactElement): void {
  expect(element.type).toBe(StudioLoginRedirect);
  (element.type as () => never)();
}

describe("Studio session guard", () => {
  it("sends a visitor without a valid session to the Studio sign-in page, keeping the page", async () => {
    vi.mocked(getSession).mockResolvedValue(null);
    const element = await StudioAppLayout({ children: <p>Projects</p> });

    expect(isValidElement(element)).toBe(true);
    expect(() => runRedirect(element)).toThrow("NEXT_REDIRECT");
    expect(navigation.redirect).toHaveBeenCalledWith(
      "/studio/login?next=%2Fstudio%2Fpapers%3Fq%3Ddepth",
    );
  });

  it("needs no `next` for the dashboard, where sign-in lands anyway", async () => {
    vi.mocked(getSession).mockResolvedValue(null);
    navigation.pathname = "/studio/dashboard";
    navigation.search = "";
    const element = await StudioAppLayout({ children: <p>Dashboard</p> });

    expect(() => runRedirect(element)).toThrow("NEXT_REDIRECT");
    expect(navigation.redirect).toHaveBeenCalledWith("/studio/login");
  });

  it("renders the shell for the signed-in user", async () => {
    vi.mocked(getSession).mockResolvedValue({
      user: { id: "u1", name: "Ada", email: "ada@lab.example", role: "admin" },
    } as never);
    const element = await StudioAppLayout({ children: <p>Dashboard content</p> });

    expect(element.type).toBe(CurrentUserProvider);
    expect((element.props as { user: unknown }).user).toEqual({
      id: "u1",
      name: "Ada",
      email: "ada@lab.example",
      role: "admin",
    });
    render(element);
    expect(screen.getByTestId("studio-shell").textContent).toBe("Dashboard content");
    expect(navigation.redirect).not.toHaveBeenCalled();
  });
});

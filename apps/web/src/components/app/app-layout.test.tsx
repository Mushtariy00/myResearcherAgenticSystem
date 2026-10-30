// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AppLayout from "@/app/(app)/layout";
import { authClient } from "@/lib/auth-client";
import { getSession } from "@/lib/session";
import { LoginRedirect } from "./login-redirect";
import { SessionRefresh } from "./session-refresh";

const navigation = vi.hoisted(() => ({
  pathname: "/runs/22222222-2222-4222-8222-222222222222",
  search: "stage=method",
  redirect: vi.fn((url: string): never => {
    throw new Error(`NEXT_REDIRECT ${url}`);
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => navigation.redirect(url),
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

vi.mock("next-intl/server", () => ({ getTranslations: vi.fn(async () => (key: string) => key) }));
vi.mock("@/lib/session", () => ({ getSession: vi.fn() }));
vi.mock("@/lib/auth-client", () => ({ authClient: { useSession: vi.fn() } }));
vi.mock("@/components/app/app-header", () => ({ AppHeader: () => null }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** The direct children of the layout's CurrentUserProvider. */
function childrenOf(element: ReactElement): ReactNode[] {
  return ([] as ReactNode[]).concat((element.props as { children: ReactNode }).children);
}

describe("the Classic app layout", () => {
  it("sends a visitor whose session is gone to sign in, and back to the page afterwards", async () => {
    vi.mocked(getSession).mockResolvedValue(null);
    const element = await AppLayout({ children: <p>Run</p> });

    expect(isValidElement(element)).toBe(true);
    expect(element.type).toBe(LoginRedirect);
    expect(() => (element.type as () => never)()).toThrow("NEXT_REDIRECT");
    expect(navigation.redirect).toHaveBeenCalledWith(
      "/login?next=%2Fruns%2F22222222-2222-4222-8222-222222222222%3Fstage%3Dmethod",
    );
  });

  it("keeps the session sliding for the signed-in user", async () => {
    vi.mocked(getSession).mockResolvedValue({
      user: { id: "u1", name: "Ada", email: "ada@lab.example", role: "user" },
    } as never);
    const element = await AppLayout({ children: <p>Run</p> });
    expect(
      childrenOf(element).some((child) => isValidElement(child) && child.type === SessionRefresh),
    ).toBe(true);

    render(<SessionRefresh />);
    expect(authClient.useSession).toHaveBeenCalled();
  });
});

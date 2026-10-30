// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { listProjectsQueryKey } from "@/client/@tanstack/react-query.gen";
import { authClient } from "@/lib/auth-client";
import { claimSignInRedirect } from "@/lib/auth-redirect";
import { StudioLoginForm } from "@/studio/components/auth/studio-login-form";
import { installDomFakes } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";
import { LoginForm } from "./login-form";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/auth-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth-client")>()),
  authClient: { signIn: { email: vi.fn(async () => ({ data: {}, error: null })) } },
}));

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function signIn() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: " grace@lab.example " } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe.each([
  ["Classic", (next: string) => <LoginForm next={next} />],
  ["Studio", (next: string) => <StudioLoginForm next={next} />],
])("signing in to %s", (_name, form) => {
  it("forgets what the tab held for the previous user, then goes on", async () => {
    const { queryClient } = renderStudio(form("/runs/r1"));
    // What user A's tab still had when A's session ended without a sign out.
    queryClient.setQueryData(listProjectsQueryKey(), [{ id: "p-of-a" }]);
    claimSignInRedirect();

    signIn();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/runs/r1"));
    expect(authClient.signIn.email).toHaveBeenCalledWith({
      email: "grace@lab.example",
      password: "correct horse",
    });
    expect(queryClient.getQueryData(listProjectsQueryKey())).toBeUndefined();
    // A 401 from now on is a new session ending: it may send the user to sign in again.
    expect(claimSignInRedirect()).toBe(true);
  });

  it("keeps the cache when the sign-in is refused", async () => {
    vi.mocked(authClient.signIn.email).mockResolvedValueOnce({
      data: null,
      error: { code: "INVALID_EMAIL_OR_PASSWORD", status: 401, statusText: "Unauthorized" },
    } as never);
    const { queryClient } = renderStudio(form("/"));
    queryClient.setQueryData(listProjectsQueryKey(), []);
    signIn();
    expect(await screen.findByText("Wrong email or password.")).toBeTruthy();
    expect(queryClient.getQueryData(listProjectsQueryKey())).toEqual([]);
    expect(router.replace).not.toHaveBeenCalled();
  });
});

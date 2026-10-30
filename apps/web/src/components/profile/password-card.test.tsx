// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MEMBER, renderAs } from "@/components/admin/test-utils";
import { authClient } from "@/lib/auth-client";
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "@/lib/password-policy";
import { StudioPasswordForm } from "@/studio/components/profile/studio-password-form";
import { StudioSessions } from "@/studio/components/profile/studio-sessions";
import { installDomFakes } from "@/studio/test/dom";
import { PasswordCard } from "./password-card";
import { SessionsCard } from "./sessions-card";
import { validatePasswordChange } from "./use-change-password-form";

vi.mock("@/lib/auth-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth-client")>()),
  authClient: {
    changePassword: vi.fn(async () => ({ data: { token: null }, error: null })),
    revokeOtherSessions: vi.fn(async () => ({ data: { status: true }, error: null })),
  },
}));

const CURRENT = "old correct horse battery";
const NEXT = "a brand new staple sentence";

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("validatePasswordChange", () => {
  const valid = { current: CURRENT, next: NEXT, confirm: NEXT };

  it("accepts a new password that follows the policy and is typed twice", () => {
    expect(validatePasswordChange(valid)).toBeNull();
    const shortest = "x".repeat(MIN_PASSWORD_LENGTH);
    expect(validatePasswordChange({ ...valid, next: shortest, confirm: shortest })).toBeNull();
  });

  it("names the problem and the field to fix", () => {
    expect(validatePasswordChange({ ...valid, current: "" })).toEqual({
      code: "currentRequired",
      field: "current",
    });
    const short = "x".repeat(MIN_PASSWORD_LENGTH - 1);
    expect(validatePasswordChange({ ...valid, next: short, confirm: short })).toEqual({
      code: "tooShort",
      field: "new",
    });
    const long = "x".repeat(MAX_PASSWORD_LENGTH + 1);
    expect(validatePasswordChange({ ...valid, next: long, confirm: long })).toEqual({
      code: "tooLong",
      field: "new",
    });
    expect(validatePasswordChange({ current: NEXT, next: NEXT, confirm: NEXT })).toEqual({
      code: "sameAsCurrent",
      field: "new",
    });
    expect(validatePasswordChange({ ...valid, confirm: `${NEXT}!` })).toEqual({
      code: "mismatch",
      field: "confirm",
    });
  });
});

function fill({ current = CURRENT, next = NEXT, confirm = NEXT } = {}) {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Repeat the new password"), {
    target: { value: confirm },
  });
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

describe.each([
  ["Classic", () => <PasswordCard />],
  ["Studio", () => <StudioPasswordForm />],
])("the %s change-password form", (_name, form) => {
  it("checks the policy before calling Better Auth, and points at the field to fix", async () => {
    renderAs(form(), { user: MEMBER });

    fill({ next: "too short", confirm: "too short" });
    expect(
      await screen.findByText(`The new password needs at least ${MIN_PASSWORD_LENGTH} characters.`),
    ).toBeTruthy();
    const next = screen.getByLabelText("New password");
    expect(next.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(next);

    fill({ confirm: `${NEXT}?` });
    expect(await screen.findByText("The two new passwords do not match.")).toBeTruthy();
    expect(screen.getByLabelText("Repeat the new password").getAttribute("aria-invalid")).toBe(
      "true",
    );

    fill({ current: NEXT });
    expect(
      await screen.findByText("Choose a new password that differs from the current one."),
    ).toBeTruthy();

    fill({ current: "" });
    expect(await screen.findByText("Enter your current password.")).toBeTruthy();
    expect(authClient.changePassword).not.toHaveBeenCalled();
  });

  it("changes the password and always signs out the other devices", async () => {
    renderAs(form(), { user: MEMBER });
    // No way to keep a device that may hold the old password signed in.
    expect(screen.queryByRole("checkbox")).toBeNull();
    fill();
    await waitFor(() =>
      expect(authClient.changePassword).toHaveBeenCalledWith({
        currentPassword: CURRENT,
        newPassword: NEXT,
        revokeOtherSessions: true,
      }),
    );
    expect(
      await screen.findByText("Password changed. Your other devices are signed out."),
    ).toBeTruthy();
    expect((screen.getByLabelText("New password") as HTMLInputElement).value).toBe("");
  });

  it("explains a wrong current password", async () => {
    vi.mocked(authClient.changePassword).mockResolvedValueOnce({
      data: null,
      error: { code: "INVALID_PASSWORD", status: 400, statusText: "Bad Request" },
    } as never);
    renderAs(form(), { user: MEMBER });
    fill();
    expect(await screen.findByText("The current password is not right.")).toBeTruthy();
    expect(screen.getByLabelText("Current password").getAttribute("aria-invalid")).toBe("true");
  });
});

describe.each([
  ["Classic", () => <SessionsCard />],
  ["Studio", () => <StudioSessions />],
])("signing out everywhere else in %s", (_name, card) => {
  it("ends every other session and says so", async () => {
    renderAs(card(), { user: MEMBER });
    fireEvent.click(screen.getByRole("button", { name: "Sign out everywhere else" }));
    expect(await screen.findByText("You are signed out everywhere except here.")).toBeTruthy();
    expect(authClient.revokeOtherSessions).toHaveBeenCalledTimes(1);
  });

  it("explains a refusal", async () => {
    vi.mocked(authClient.revokeOtherSessions).mockResolvedValueOnce({
      data: null,
      error: { status: 429, statusText: "Too Many Requests" },
    } as never);
    renderAs(card(), { user: MEMBER });
    fireEvent.click(screen.getByRole("button", { name: "Sign out everywhere else" }));
    expect(await screen.findByText("Could not sign out your other devices")).toBeTruthy();
    expect(screen.getByText("Too many attempts. Wait a moment and try again.")).toBeTruthy();
  });
});

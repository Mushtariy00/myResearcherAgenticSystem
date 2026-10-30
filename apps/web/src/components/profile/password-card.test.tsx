// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MEMBER, renderAs } from "@/components/admin/test-utils";
import { authClient } from "@/lib/auth-client";
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "@/lib/password-policy";
import { StudioPasswordForm } from "@/studio/components/profile/studio-password-form";
import { installDomFakes } from "@/studio/test/dom";
import { PasswordCard } from "./password-card";
import { validatePasswordChange } from "./use-change-password-form";

vi.mock("@/lib/auth-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth-client")>()),
  authClient: { changePassword: vi.fn(async () => ({ data: { token: null }, error: null })) },
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

  it("changes the password and signs out the other devices by default", async () => {
    renderAs(form(), { user: MEMBER });
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

  it("can keep the other devices signed in", async () => {
    renderAs(form(), { user: MEMBER });
    fireEvent.click(screen.getByLabelText("Sign me out on my other devices"));
    fill();
    await waitFor(() =>
      expect(authClient.changePassword).toHaveBeenCalledWith(
        expect.objectContaining({ revokeOtherSessions: false }),
      ),
    );
    expect(await screen.findByText("Password changed.")).toBeTruthy();
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

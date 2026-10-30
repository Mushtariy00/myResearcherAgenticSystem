// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { restoreUser, signOutEverywhere, suspendUser } from "@/lib/admin-offboarding";
import { installDomFakes } from "@/studio/test/dom";
import { LAB_ADMIN, renderAs } from "./test-utils";
import type { LabUser } from "./use-lab-users";
import { UserActionsMenu } from "./user-actions-menu";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/lib/admin-offboarding", () => ({
  suspendUser: vi.fn(async () => ({ ok: true })),
  restoreUser: vi.fn(async () => ({ ok: true })),
  signOutEverywhere: vi.fn(async () => ({ ok: true })),
}));

const GRACE: LabUser = {
  id: "user-grace",
  name: "Grace Hopper",
  email: "grace@lab.example",
  role: "user",
  banned: false,
  createdAt: "2026-10-01T00:00:00Z",
};

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderMenu(user: LabUser = GRACE, { isSelf = false } = {}) {
  const onPasswordLink = vi.fn();
  const view = renderAs(
    <UserActionsMenu user={user} isSelf={isSelf} onPasswordLink={onPasswordLink} />,
    { user: LAB_ADMIN },
  );
  return { ...view, onPasswordLink };
}

async function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "Actions for Grace Hopper" }));
  return screen.findByRole("menu");
}

/** Picks a menu item as a mouse would (press, then click). */
function pick(item: HTMLElement) {
  fireEvent.pointerDown(item);
  fireEvent.click(item);
}

async function choose(name: RegExp) {
  const menu = await openMenu();
  pick(within(menu).getByRole("menuitem", { name }));
}

describe("UserActionsMenu offboarding", () => {
  it("suspends an account only after the admin confirms", async () => {
    renderMenu();
    await choose(/Suspend access/);
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Suspend Grace Hopper?")).toBeTruthy();
    expect(
      within(dialog).getByText(/grace@lab\.example will no longer be able to sign in/),
    ).toBeTruthy();
    expect(suspendUser).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(suspendUser).not.toHaveBeenCalled();

    await choose(/Suspend access/);
    fireEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Suspend and sign out",
      }),
    );
    await waitFor(() => expect(suspendUser).toHaveBeenCalledWith({ userId: GRACE.id }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Grace Hopper is suspended and signed out everywhere.",
      ),
    );
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  });

  it("keeps the dialog open with the reason when the action is refused", async () => {
    vi.mocked(suspendUser).mockResolvedValueOnce({
      ok: false,
      code: "YOU_ARE_NOT_ALLOWED_TO_BAN_USERS",
    });
    renderMenu();
    await choose(/Suspend access/);
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Suspend and sign out" }));
    expect(
      await within(dialog).findByText("Only lab admins can suspend or restore accounts."),
    ).toBeTruthy();
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("signs someone out everywhere after confirmation", async () => {
    renderMenu();
    await choose(/Sign out everywhere/);
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Sign Grace Hopper out everywhere?")).toBeTruthy();
    expect(signOutEverywhere).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Sign out everywhere" }));
    await waitFor(() => expect(signOutEverywhere).toHaveBeenCalledWith({ userId: GRACE.id }));
  });

  it("restores a suspended account after confirmation", async () => {
    renderMenu({ ...GRACE, banned: true });
    const menu = await openMenu();
    expect(within(menu).queryByRole("menuitem", { name: /Suspend access/ })).toBeNull();
    pick(within(menu).getByRole("menuitem", { name: /Restore access/ }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore access" }));
    await waitFor(() => expect(restoreUser).toHaveBeenCalledWith({ userId: GRACE.id }));
  });

  it("offers no offboarding of the admin's own account, but still a password link", async () => {
    const { onPasswordLink } = renderMenu(GRACE, { isSelf: true });
    const menu = await openMenu();
    const item = (name: RegExp) => within(menu).getByRole("menuitem", { name });
    expect(item(/Suspend access/).getAttribute("aria-disabled")).toBe("true");
    expect(item(/Sign out everywhere/).getAttribute("aria-disabled")).toBe("true");
    pick(item(/Send a password link/));
    expect(onPasswordLink).toHaveBeenCalledWith(GRACE);
  });
});

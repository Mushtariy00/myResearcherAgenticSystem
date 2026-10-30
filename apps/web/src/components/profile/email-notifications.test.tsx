// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { MySettingsIn, MySettingsOut } from "@/client";
import { MEMBER, renderAs } from "@/components/admin/test-utils";
import { LocaleSwitcher } from "@/components/app/locale-switcher";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import { setLocale } from "@/i18n/actions";
import { StudioEmailNotifications } from "@/studio/components/profile/studio-email-notifications";
import { StudioPreferences } from "@/studio/components/profile/studio-preferences";
import { installDomFakes } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";
import { EmailNotificationsCard } from "./email-notifications-card";
import { PreferencesCard } from "./preferences-card";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/profile" }));
vi.mock("@/i18n/actions", () => ({ setLocale: vi.fn(async () => {}) }));

const SETTINGS = "/api/v1/me/settings";

/** The server's settings: saves stick, as they would in the API, unless `refuse` is set. */
let stored: MySettingsOut;
let puts: MySettingsIn[];
let refuse: boolean;
let fetchMock: ReturnType<typeof mockApi>;

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  stored = { email_notifications: true, locale: "en" };
  puts = [];
  refuse = false;
  fetchMock = mockApi(async (request, path) => {
    if (path !== SETTINGS) {
      return json(404, { detail: "unknown" });
    }
    if (request.method === "PUT") {
      const body = (await request.json()) as MySettingsIn;
      puts.push(body);
      if (refuse) {
        return json(503, { detail: "db.unavailable" });
      }
      stored = {
        email_notifications: body.email_notifications ?? stored.email_notifications,
        locale: body.locale ?? stored.locale,
      };
    }
    return json(200, stored);
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function emailSwitch(): HTMLElement {
  return screen.getByRole("switch", { name: "Email me" });
}

/** Waits until the switch shows `checked` and takes clicks again (no save on its way). */
async function settled(checked: boolean) {
  await waitFor(() => {
    expect(emailSwitch().getAttribute("aria-checked")).toBe(String(checked));
    expect(emailSwitch().hasAttribute("data-disabled")).toBe(false);
  });
}

describe.each([
  ["Classic", () => <EmailNotificationsCard />],
  ["Studio", () => <StudioEmailNotifications />],
])("the %s email notifications switch", (_name, card) => {
  it("shows the saved setting and turns the emails off and on again", async () => {
    renderAs(card(), { user: MEMBER });
    await screen.findByRole("switch", { name: "Email me" });
    await settled(true);
    expect(
      screen.getByText(
        "Emails go to ada@lab.example, in the language you choose for the interface.",
      ),
    ).toBeTruthy();

    fireEvent.click(emailSwitch());
    await settled(false);
    expect(puts).toEqual([{ email_notifications: false }]);
    fireEvent.click(emailSwitch());
    await settled(true);
    expect(puts).toEqual([{ email_notifications: false }, { email_notifications: true }]);
  });

  it("puts a refused change back and says why", async () => {
    refuse = true;
    renderAs(card(), { user: MEMBER });
    await screen.findByRole("switch", { name: "Email me" });
    fireEvent.click(emailSwitch());
    expect(await screen.findByText("Could not save your email setting")).toBeTruthy();
    await settled(true);
    expect(puts).toEqual([{ email_notifications: false }]);
  });
});

describe.each([
  ["Classic", () => <PreferencesCard />],
  ["Studio", () => <StudioPreferences />],
])("choosing a language on the %s profile page", (_name, card) => {
  it("switches the interface and saves the language of the emails", async () => {
    renderAs(card(), { user: MEMBER });
    fireEvent.click(screen.getByRole("radio", { name: "한국어" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalledTimes(1));
    expect(setLocale).toHaveBeenCalledWith("ko");
    await waitFor(() => expect(puts).toEqual([{ locale: "ko" }]));
  });

  it("saves nothing when the language stays the same", async () => {
    renderAs(card(), { user: MEMBER });
    fireEvent.click(screen.getByRole("radio", { name: "English" }));
    expect(setLocale).not.toHaveBeenCalled();
    expect(puts).toEqual([]);
  });
});

describe("the header's language switch", () => {
  async function chooseKorean() {
    fireEvent.click(screen.getByRole("button", { name: "Language" }));
    fireEvent.click(await screen.findByRole("menuitemradio", { name: "한국어" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalledTimes(1));
    expect(setLocale).toHaveBeenCalledWith("ko");
  }

  it("also saves the language of a signed-in user's emails", async () => {
    renderAs(<LocaleSwitcher />, { user: MEMBER });
    await chooseKorean();
    await waitFor(() => expect(puts).toEqual([{ locale: "ko" }]));
  });

  it("only switches the interface on the sign-in pages", async () => {
    renderStudio(<LocaleSwitcher />);
    await chooseKorean();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

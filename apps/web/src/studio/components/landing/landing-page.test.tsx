// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import StudioLandingPage from "@/app/studio/page";
import { getSession } from "@/lib/session";
import { installDomFakes } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";
import { LandingCapabilities } from "./capabilities";
import { LandingHowItWorks } from "./how-it-works";
import { DATA_SOURCES } from "./sources";

vi.mock("@/lib/session", () => ({ getSession: vi.fn() }));
vi.mock("@/i18n/actions", () => ({ setLocale: vi.fn(async () => {}) }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/studio",
}));

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
});

async function renderLanding(locale: "en" | "ko" = "en") {
  return renderStudio(await StudioLandingPage(), { locale });
}

describe("Studio landing page", () => {
  it("renders for a visitor without a session and offers sign-in", async () => {
    vi.mocked(getSession).mockResolvedValue(null);
    await renderLanding();

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "From a research questionto a reviewed paper",
    );
    const signIn = screen.getAllByRole("link", { name: /^Sign in/ });
    expect(signIn.length).toBeGreaterThan(0);
    for (const link of signIn) {
      expect(link.getAttribute("href")).toBe("/studio/login");
    }
    expect(screen.queryByRole("link", { name: /Open dashboard/ })).toBeNull();
    expect(screen.getByText("Accounts are created by invitation from a lab admin.")).toBeTruthy();
  });

  it("offers the dashboard to a signed-in visitor", async () => {
    vi.mocked(getSession).mockResolvedValue({ user: { id: "u1" } } as never);
    await renderLanding();
    const open = screen.getAllByRole("link", { name: /^Open dashboard/ });
    expect(open[0]?.getAttribute("href")).toBe("/studio/dashboard");
    expect(screen.queryByRole("link", { name: /^Sign in/ })).toBeNull();
  });

  it("still renders, signed out, when the session check fails", async () => {
    vi.mocked(getSession).mockRejectedValue(new Error("auth database unavailable"));
    await renderLanding();
    expect(screen.getAllByRole("link", { name: /^Sign in/ }).length).toBeGreaterThan(0);
  });

  it("shows the pipeline demo, the capabilities and every data source", async () => {
    vi.mocked(getSession).mockResolvedValue(null);
    await renderLanding();

    const pipeline = screen.getByRole("list", { name: "Pipeline stages" });
    expect(within(pipeline).getAllByRole("listitem")).toHaveLength(5);
    expect(
      screen.getByText("An illustration of how a run moves through the pipeline, not live data."),
    ).toBeTruthy();

    for (const title of [
      "Five stages, one pipeline",
      "A person approves every step",
      "Paid models within budget, free models otherwise",
      "GPU sandbox with provenance",
      "English and Korean",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    }

    const sources = screen.getByRole("list", { name: "Data sources" });
    for (const source of DATA_SOURCES) {
      expect(within(sources).getByText(source)).toBeTruthy();
    }
    expect(screen.getByRole("link", { name: /Open Classic/ }).getAttribute("href")).toBe("/");
  });

  it("wraps the product name in the header instead of cutting it off on phones", async () => {
    vi.mocked(getSession).mockResolvedValue(null);
    await renderLanding();
    const header = screen.getByRole("banner");
    const brand = within(header).getByRole("link", { name: /Agentic Research Platform/ });
    expect(brand.getAttribute("href")).toBe("/studio");
    const name = within(brand).getByText("Agentic Research Platform");
    expect(name.className).not.toMatch(/(^|\s)(truncate|whitespace-nowrap|line-clamp-\d)(\s|$)/);
    expect(name.className).toMatch(/text-balance/);
  });

  it("is translated into Korean", async () => {
    vi.mocked(getSession).mockResolvedValue(null);
    await renderLanding("ko");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "연구 질문에서검토를 마친 논문까지",
    );
    expect(screen.getAllByRole("link", { name: /^로그인/ }).length).toBeGreaterThan(0);
  });
});

/** The column span a class list gives at the first of `breakpoints` that sets one. */
function spanAt(className: string, breakpoints: readonly string[]): number {
  for (const breakpoint of breakpoints) {
    const match = new RegExp(`(?:^|\\s)${breakpoint}:col-span-(\\d+)(?:\\s|$)`).exec(className);
    if (match?.[1]) {
      return Number(match[1]);
    }
  }
  return 1;
}

/** Cells left empty when one-row cards are auto-placed in order (sparse, as CSS grid does). */
function emptyCells(spans: readonly number[], columns: number): number {
  let used = 0;
  let empty = 0;
  for (const span of spans) {
    if (used + span > columns) {
      empty += columns - used;
      used = 0;
    }
    used = (used + span) % columns;
  }
  return empty + (used === 0 ? 0 : columns - used);
}

describe("Studio landing layout", () => {
  it("fills every row of the capabilities grid on tablets and desktops", () => {
    renderStudio(<LandingCapabilities />);
    const section = screen.getByRole("region", { name: "Built for careful research" });
    const cards = Array.from(section.querySelector("ul")?.children ?? [], (card) => card.className);
    expect(cards).toHaveLength(5);
    const tablet = cards.map((card) => spanAt(card, ["sm"]));
    const desktop = cards.map((card) => spanAt(card, ["lg", "sm"]));
    expect(emptyCells(tablet, 2), "two columns").toBe(0);
    expect(emptyCells(desktop, 6), "six tracks").toBe(0);
  });

  it("joins each how-it-works step to the next inside a valid list", () => {
    renderStudio(<LandingHowItWorks />);
    const steps = screen.getByRole("list");
    expect(Array.from(steps.children, (child) => child.tagName)).toEqual(["LI", "LI", "LI", "LI"]);
    // A connector leaves every card but the last, towards the next one.
    expect(
      Array.from(steps.children, (step) => step.querySelectorAll("[data-connector]").length),
    ).toEqual([1, 1, 1, 0]);
  });
});

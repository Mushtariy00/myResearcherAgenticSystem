// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AuditPage,
  BudgetOut,
  LabBalanceOut,
  ModelRoutingOut,
  SystemHealthOut,
} from "@/client";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import { StudioAdminView } from "@/studio/components/admin/studio-admin-view";
import { installDomFakes } from "@/studio/test/dom";
import type { AdminTab } from "./admin-sections";
import { AdminView } from "./admin-view";
import { LAB_ADMIN, renderAs } from "./test-utils";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock("@/lib/admin-actions", () => ({ inviteUser: vi.fn(), sendPasswordLink: vi.fn() }));
vi.mock("@/lib/admin-offboarding", () => ({
  suspendUser: vi.fn(),
  restoreUser: vi.fn(),
  signOutEverywhere: vi.fn(),
}));
vi.mock("@/lib/auth-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth-client")>()),
  authClient: {
    admin: {
      listUsers: vi.fn(async () => ({
        data: {
          users: [
            {
              id: "user-admin",
              name: "Katherine Johnson",
              email: "katherine@lab.example",
              role: "admin",
              banned: false,
              createdAt: "2026-09-01T00:00:00Z",
            },
            {
              id: "user-grace",
              name: "Grace Hopper",
              email: "grace@lab.example",
              role: "user",
              banned: true,
              createdAt: "2026-10-01T00:00:00Z",
            },
          ],
        },
        error: null,
      })),
    },
  },
}));

const ROUTING: ModelRoutingOut = {
  paid_models_enabled: false,
  demo: true,
  roles: [
    {
      role: "screener",
      max_output_tokens: 800,
      paid: [
        {
          id: "google/gemini-2.5-flash",
          free: false,
          in_catalog: true,
          context_length: 1_048_576,
          prompt_usd_per_mtok: "0.30",
          completion_usd_per_mtok: "2.50",
        },
        {
          id: "acme/unknown-model",
          free: false,
          in_catalog: false,
          context_length: null,
          prompt_usd_per_mtok: null,
          completion_usd_per_mtok: null,
        },
      ],
      free: [
        {
          id: "google/gemma-4-31b-it:free",
          free: true,
          in_catalog: true,
          context_length: 131_072,
          prompt_usd_per_mtok: "0",
          completion_usd_per_mtok: "0",
        },
      ],
    },
  ],
};

const BALANCE: LabBalanceOut = {
  balance_usd: "8.50",
  month: "2026-10",
  spent_this_month_usd: "31.50",
  free_daily_limit: 1000,
  free_calls_today: 950,
  auto_top_up: false,
  alert_floor_usd: "10.00",
  below_floor: true,
  checked_at: new Date().toISOString(),
  demo: true,
};

const HEALTH: SystemHealthOut = {
  status: "down",
  checked_at: new Date().toISOString(),
  checks: [
    { name: "postgres", status: "ok", latency_ms: 2.5, detail: null },
    { name: "temporal", status: "down", latency_ms: 2000, detail: "health.timeout" },
    { name: "worker", status: "unknown", latency_ms: 1.2, detail: "health.unsupported" },
    { name: "gateway", status: "degraded", latency_ms: 1300, detail: "gateway.weird" },
  ],
};

const AUDIT: AuditPage = {
  total: 2,
  items: [
    {
      id: 2,
      actor_id: "user-admin",
      actor_name: "Katherine Johnson",
      actor_email: "katherine@lab.example",
      action: "budget.set",
      target_type: "user",
      target_id: "user-grace",
      details: { monthly_usd: "20.00" },
      created_at: new Date(Date.now() - 60_000).toISOString(),
    },
    {
      id: 1,
      actor_id: "ghost",
      actor_name: null,
      actor_email: null,
      action: "future.action",
      target_type: "project",
      target_id: "33333333-3333-4333-8333-333333333333",
      details: { name: "Depth lab" },
      created_at: new Date(Date.now() - 3_600_000).toISOString(),
    },
  ],
};

const BUDGETS: BudgetOut[] = [{ user_id: "user-grace", monthly_usd: "20.00", spent_usd: "5.00" }];

const RESPONSES: Record<string, unknown> = {
  "/api/v1/admin/models": ROUTING,
  "/api/v1/admin/balance": BALANCE,
  "/api/v1/admin/health": HEALTH,
  "/api/v1/admin/audit": AUDIT,
  "/api/v1/admin/budgets": BUDGETS,
  "/api/v1/admin/settings/paid-models": { enabled: false },
};

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  mockApi((_request, path) =>
    path in RESPONSES ? json(200, RESPONSES[path]) : json(404, { detail: "unknown" }),
  );
});

afterEach(() => {
  cleanup();
});

const views: [string, (tab: AdminTab) => ReactElement][] = [
  ["Classic", (tab) => <AdminView initialTab={tab} />],
  ["Studio", (tab) => <StudioAdminView initialTab={tab} />],
];

describe.each(views)("the %s admin sections", (_name, view) => {
  const open = (tab: AdminTab) => renderAs(view(tab), { user: LAB_ADMIN });

  it("lists the users with their status and actions, next to the invite form", async () => {
    open("users");
    expect(await screen.findByText("Grace Hopper")).toBeTruthy();
    expect(screen.getByText("Suspended")).toBeTruthy();
    expect(screen.getByText("You")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Actions for Grace Hopper" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send invitation" })).toBeTruthy();
  });

  it("edits budgets inline and shows the paid-models switch", async () => {
    open("budgets");
    const field = (await screen.findByLabelText(
      "Monthly budget for Grace Hopper, in USD",
    )) as HTMLInputElement;
    expect(field.value).toBe("20");
    expect(screen.getByText("$5.00")).toBeTruthy();
    expect(await screen.findByText("Paid models off: free models only")).toBeTruthy();
  });

  it("shows each role's model chains with prices, and that paid models are off", async () => {
    open("routing");
    expect(await screen.findByText("Screener")).toBeTruthy();
    expect(screen.getByText("google/gemini-2.5-flash")).toBeTruthy();
    expect(
      screen.getByText("$0.30 in · $2.50 out per million tokens · 1M tokens of context"),
    ).toBeTruthy();
    expect(screen.getByText("Not in the model catalog: price and context unknown")).toBeTruthy();
    expect(screen.getByText("Free · 131K tokens of context")).toBeTruthy();
    expect(screen.getAllByText(/Skipped while paid models are off/).length).toBeGreaterThan(0);
    expect(screen.getByText("Up to 800 output tokens per call")).toBeTruthy();
    expect(screen.getAllByText("Demo").length).toBeGreaterThan(0);
  });

  it("shows the balance gauge, the low-balance alert and today's free calls", async () => {
    open("balance");
    const gauge = await screen.findByRole("meter", { name: "Lab balance" });
    expect(gauge.getAttribute("aria-valuetext")).toBe("$8.50 left, 21% of this month's funds");
    expect(screen.getByText(/The balance is low/)).toBeTruthy();
    expect(screen.getByText("Spent in October 2026")).toBeTruthy();
    expect(screen.getByText("950 of 1,000 calls")).toBeTruthy();
    expect(
      screen
        .getByRole("progressbar", { name: "Free-model calls today" })
        .getAttribute("aria-valuenow"),
    ).toBe("950");
  });

  it("translates every health detail, and shows unknown ones as they are", async () => {
    open("health");
    expect(await screen.findByText("Workflow engine (Temporal)")).toBeTruthy();
    expect(screen.getByText("No answer within 2 seconds.")).toBeTruthy();
    expect(screen.getByText("The workflow engine cannot report its workers.")).toBeTruthy();
    expect(screen.getByText("gateway.weird")).toBeTruthy();
    expect(screen.getAllByText("Down").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Healthy").length).toBeGreaterThan(0);
  });

  it("names audit actions and targets, falls back to raw names, and expands details", async () => {
    open("audit");
    expect((await screen.findAllByText("Set a monthly budget")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Grace Hopper")).toBeTruthy();
    expect(screen.getAllByText("future.action").length).toBeGreaterThan(0);
    expect(screen.getByText("Depth lab")).toBeTruthy();
    expect(screen.getByText("Unknown user")).toBeTruthy();
    expect(screen.getByText("1–2 of 2")).toBeTruthy();

    const toggle = screen.getAllByRole("button", { name: /^Details: Set a monthly budget/ })[0];
    fireEvent.click(toggle as HTMLElement);
    const details = await screen.findByRole("region", {
      name: /^Recorded details: Set a monthly budget/,
    });
    expect(within(details).getByText(/"monthly_usd": "20.00"/)).toBeTruthy();
    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
  });
});

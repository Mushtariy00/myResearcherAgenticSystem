// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AuditPage,
  BudgetOut,
  LabBalanceOut,
  ModelCatalogOut,
  ModelRoutingOut,
  RoutedModelOut,
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

const GEMINI: RoutedModelOut = {
  id: "google/gemini-2.5-flash",
  free: false,
  in_catalog: true,
  context_length: 1_048_576,
  prompt_usd_per_mtok: "0.30",
  completion_usd_per_mtok: "2.50",
};
const UNKNOWN_MODEL: RoutedModelOut = {
  id: "acme/unknown-model",
  free: false,
  in_catalog: false,
  context_length: null,
  prompt_usd_per_mtok: null,
  completion_usd_per_mtok: null,
};
const GEMMA: RoutedModelOut = {
  id: "google/gemma-4-31b-it:free",
  free: true,
  in_catalog: true,
  context_length: 131_072,
  prompt_usd_per_mtok: "0",
  completion_usd_per_mtok: "0",
};
const SONNET: RoutedModelOut = {
  id: "anthropic/claude-sonnet-4.5",
  free: false,
  in_catalog: true,
  context_length: 1_000_000,
  prompt_usd_per_mtok: "3",
  completion_usd_per_mtok: "15",
};

const SCREENER = {
  role: "screener",
  max_output_tokens: 800,
  paid: [GEMINI, UNKNOWN_MODEL],
  free: [GEMMA],
  paid_is_lab_default: true,
  free_is_lab_default: true,
} as const satisfies ModelRoutingOut["roles"][number];

const ROUTING: ModelRoutingOut = {
  paid_models_enabled: false,
  demo: false,
  roles: [{ ...SCREENER, paid: [...SCREENER.paid], free: [...SCREENER.free] }],
  lab_paid: [GEMINI, UNKNOWN_MODEL],
  lab_free: [GEMMA],
  catalog_checked_at: new Date().toISOString(),
};

const CATALOG: ModelCatalogOut = {
  checked_at: new Date().toISOString(),
  models: [SONNET, GEMINI, GEMMA],
};

const BALANCE: LabBalanceOut = {
  balance_usd: "8.50",
  free_tier: false,
  month: "2026-10",
  spent_this_month_usd: "31.50",
  free_daily_limit: 1000,
  free_calls_today: 950,
  auto_top_up: false,
  alert_floor_usd: "10.00",
  below_floor: true,
  checked_at: new Date().toISOString(),
  demo: false,
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
  "/api/v1/admin/models/catalog": CATALOG,
  "/api/v1/admin/balance": BALANCE,
  "/api/v1/admin/health": HEALTH,
  "/api/v1/admin/audit": AUDIT,
  "/api/v1/admin/budgets": BUDGETS,
  "/api/v1/admin/settings/paid-models": { enabled: false },
};

/** The usual answers with some replaced, after `first` has had its say (null: go on). */
function answering(
  overrides: Record<string, unknown>,
  first: (request: Request, path: string) => Response | null | Promise<Response | null> = () =>
    null,
) {
  const responses = { ...RESPONSES, ...overrides };
  mockApi(async (request, path) => {
    const answer = await first(request, path);
    if (answer) {
      return answer;
    }
    return path in responses ? json(200, responses[path]) : json(404, { detail: "unknown" });
  });
}

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

  it("shows no budgets or spend rather than zeros when the budgets fail to load", async () => {
    mockApi((_request, path) =>
      path === "/api/v1/admin/budgets"
        ? json(503, { detail: "db.unavailable" })
        : path in RESPONSES
          ? json(200, RESPONSES[path])
          : json(404, { detail: "unknown" }),
    );
    open("budgets");
    expect(await screen.findByText("The database is unavailable. Try again shortly.")).toBeTruthy();
    expect((await screen.findAllByText("Grace Hopper")).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Monthly budget for Grace Hopper, in USD")).toBeNull();
    expect(screen.queryByText("$0.00")).toBeNull();
    expect(
      screen.getAllByText("Unknown, because the budgets did not load", { exact: false }).length,
    ).toBeGreaterThan(0);
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
    expect(screen.queryByText("Demo")).toBeNull();
    expect(screen.queryByText("This role's own list")).toBeNull();
  });

  it("says when the gateway has not read the model catalog yet", async () => {
    answering({ "/api/v1/admin/models": { ...ROUTING, catalog_checked_at: null } });
    open("routing");
    expect(await screen.findByText(/has not read OpenRouter's model list yet/)).toBeTruthy();
  });

  it("gives a role its own paid chain: starts from today's, reorders, trims, adds", async () => {
    const saved: unknown[] = [];
    const after: ModelRoutingOut = {
      ...ROUTING,
      roles: [{ ...SCREENER, paid: [SONNET, GEMINI], free: [GEMMA], paid_is_lab_default: false }],
    };
    answering({}, async (request, path) => {
      if (request.method === "PUT" && path === "/api/v1/admin/models/screener") {
        saved.push(await request.json());
        return json(200, after);
      }
      return null;
    });
    open("routing");
    fireEvent.click(await screen.findByRole("button", { name: "Edit models for Screener" }));
    const dialog = await screen.findByRole("dialog", { name: "Models for Screener" });
    const save = within(dialog).getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // nothing to save yet

    fireEvent.click(within(dialog).getByRole("switch", { name: "Paid models Use the lab's list" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove acme/unknown-model" }));
    fireEvent.change(await within(dialog).findByLabelText("Search models to add"), {
      target: { value: "sonnet" },
    });
    fireEvent.click(
      await within(dialog).findByRole("button", { name: "Add anthropic/claude-sonnet-4.5" }),
    );
    // The chain's other models aren't offered twice, and free models aren't offered here at all.
    fireEvent.change(within(dialog).getByLabelText("Search models to add"), {
      target: { value: "" },
    });
    expect(within(dialog).queryByRole("button", { name: /^Add google/ })).toBeNull();

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Move anthropic/claude-sonnet-4.5 up" }),
    );
    expect(save.disabled).toBe(false);
    fireEvent.click(save);

    await waitFor(() =>
      expect(saved).toEqual([
        { paid: ["anthropic/claude-sonnet-4.5", "google/gemini-2.5-flash"], free: null },
      ]),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("This role's own list")).toBeTruthy();
    expect(screen.getByText("anthropic/claude-sonnet-4.5")).toBeTruthy();
  });

  it("lets a role stay on free models, but never without free models", async () => {
    open("routing");
    fireEvent.click(await screen.findByRole("button", { name: "Edit models for Screener" }));
    const dialog = await screen.findByRole("dialog", { name: "Models for Screener" });
    const save = within(dialog).getByRole("button", { name: "Save" }) as HTMLButtonElement;

    fireEvent.click(within(dialog).getByRole("switch", { name: "Paid models Use the lab's list" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove acme/unknown-model" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove google/gemini-2.5-flash" }));
    expect(
      within(dialog).getByText("No paid models: this role stays on free models."),
    ).toBeTruthy();
    expect(save.disabled).toBe(false);

    fireEvent.click(within(dialog).getByRole("switch", { name: "Free models Use the lab's list" }));
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Remove google/gemma-4-31b-it:free" }),
    );
    expect(
      within(dialog).getByText("Add at least one free model: the role falls back to these."),
    ).toBeTruthy();
    expect(save.disabled).toBe(true);
  });

  it("explains a chain the API refuses and keeps the dialog open", async () => {
    answering({}, (request, path) =>
      request.method === "PUT" && path === "/api/v1/admin/models/screener"
        ? json(422, { detail: "routing.unknown_model" })
        : null,
    );
    open("routing");
    fireEvent.click(await screen.findByRole("button", { name: "Edit models for Screener" }));
    const dialog = await screen.findByRole("dialog", { name: "Models for Screener" });
    fireEvent.click(within(dialog).getByRole("switch", { name: "Paid models Use the lab's list" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText(/OpenRouter no longer offers one/)).toBeTruthy();
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

  it("has no gauge or alert on the free tier, and says what buying credit changes", async () => {
    answering({
      "/api/v1/admin/balance": {
        ...BALANCE,
        balance_usd: "0",
        free_tier: true,
        free_daily_limit: 50,
        free_calls_today: 3,
        below_floor: false,
      },
    });
    open("balance");
    expect(await screen.findByText(/Free tier: only free models work/)).toBeTruthy();
    expect(screen.getByText(/raises free calls from 50 to 1,000 a day/)).toBeTruthy();
    expect(screen.getByText("3 of 50 calls")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
    expect(screen.queryByText(/The balance is low/)).toBeNull();
  });

  it("shows a balance nobody has read as unknown, not as zero", async () => {
    answering({
      "/api/v1/admin/balance": {
        ...BALANCE,
        balance_usd: null,
        checked_at: null,
        below_floor: false,
      },
    });
    open("balance");
    expect(await screen.findByText(/Not read yet/)).toBeTruthy();
    expect(screen.getByText("Not yet")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
    expect(screen.queryByText(/The balance is low/)).toBeNull();
  });

  it("says when OpenRouter would not report a balance", async () => {
    answering({ "/api/v1/admin/balance": { ...BALANCE, balance_usd: null, below_floor: false } });
    open("balance");
    expect(await screen.findByText(/Balance unknown/)).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
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

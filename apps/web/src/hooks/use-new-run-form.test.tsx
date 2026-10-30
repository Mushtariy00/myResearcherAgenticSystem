// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunEstimateOut, RunOut } from "@/client";
import { listRecentRunsQueryKey, listRunsQueryKey } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { type UseNewRunFormOptions, useNewRunForm } from "./use-new-run-form";

const PROJECT = "33333333-3333-4333-8333-333333333333";

const ESTIMATE: RunEstimateOut = {
  llm_policy: "auto",
  low_usd: "0.08",
  expected_usd: "0.21",
  high_usd: "0.55",
  calls_low: 30,
  expected_calls: 42,
  calls_high: 60,
  paid_possible: true,
  paid_blocked_by: null,
  paid_models_enabled: true,
  budget_remaining_usd: "18.00",
  capped_by: null,
  assumptions: { paid_chain: [], steps: [] },
  demo: true,
};

const RUN: RunOut = {
  id: "22222222-2222-4222-8222-222222222222",
  project_id: PROJECT,
  owner_id: "user-1",
  topic: "Monocular depth estimation",
  status: "queued",
  llm_policy: "auto",
  budget_cap_usd: null,
  config: { ...RUN_CONFIG_DEFAULTS },
  error: null,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
};

type Call = { method: string; path: string; body: unknown };

const fetchMock = vi.fn<typeof fetch>();
let calls: Call[] = [];
let createResponse: () => Response;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const estimates = () => calls.filter((call) => call.path === "/api/v1/runs/estimate");
const creations = () => calls.filter((call) => call.path === `/api/v1/projects/${PROJECT}/runs`);

beforeEach(() => {
  calls = [];
  createResponse = () => json(201, RUN);
  configureApiClient();
  // Node's Request needs an absolute URL; the browser resolves "/api/v1/..." itself.
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    calls.push({
      method: request.method,
      path,
      body: request.method === "GET" ? undefined : await request.json(),
    });
    if (path === "/api/v1/runs/estimate") {
      return json(200, ESTIMATE);
    }
    if (path === `/api/v1/projects/${PROJECT}/runs`) {
      return createResponse();
    }
    return json(404, { detail: "run.not_found" });
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup(options: UseNewRunFormOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useNewRunForm(PROJECT, { estimateDebounceMs: 20, ...options }), {
    wrapper,
  });
  return { ...view, queryClient };
}

describe("useNewRunForm steps", () => {
  it("validates the current step before moving on", async () => {
    const { result } = setup();
    expect(result.current.step.id).toBe("topic");
    expect(result.current.isFirstStep).toBe(true);

    let moved = true;
    await act(async () => {
      moved = await result.current.next();
    });
    expect(moved).toBe(false);
    expect(result.current.stepIndex).toBe(0);
    expect(result.current.form.formState.errors.topic?.message).toBe("topic.tooShort");
    expect(result.current.stepErrors).toEqual({
      topic: true,
      literature: false,
      stages: false,
      budget: false,
    });

    act(() => result.current.form.setValue("topic", "Monocular depth estimation"));
    await act(async () => {
      moved = await result.current.next();
    });
    expect(moved).toBe(true);
    expect(result.current.step.id).toBe("literature");
  });

  it("jumps forward only past valid steps, and back at once", async () => {
    const { result } = setup();
    let moved = true;
    await act(async () => {
      moved = await result.current.goTo("budget");
    });
    expect(moved).toBe(false);
    expect(result.current.step.id).toBe("topic");

    act(() => result.current.form.setValue("topic", "Monocular depth estimation"));
    await act(async () => {
      moved = await result.current.goTo("budget");
    });
    expect(moved).toBe(true);
    expect(result.current.isLastStep).toBe(true);

    act(() => result.current.back());
    expect(result.current.step.id).toBe("stages");
    await act(async () => {
      await result.current.goTo("topic");
    });
    expect(result.current.stepIndex).toBe(0);
  });

  it("moves on instead of submitting when Enter is pressed on an earlier step", async () => {
    const { result } = setup();
    act(() => result.current.form.setValue("topic", "Monocular depth estimation"));
    const preventDefault = vi.fn();
    await act(async () => {
      await result.current.onSubmit({ preventDefault } as never);
    });
    expect(preventDefault).toHaveBeenCalled();
    expect(result.current.step.id).toBe("literature");
    expect(creations()).toHaveLength(0);
  });

  it("re-checks the year order when the first year changes", async () => {
    const { result } = setup();
    act(() => result.current.form.setValue("config.year_to", 2020, { shouldTouch: true }));
    act(() => result.current.form.setValue("config.year_from", 2025));
    await waitFor(() =>
      expect(result.current.form.formState.errors.config?.year_to?.message).toBe("year.order"),
    );
    act(() => result.current.form.setValue("config.year_from", 2019));
    await waitFor(() =>
      expect(result.current.form.formState.errors.config?.year_to).toBeUndefined(),
    );
  });

  it("sets the stages to a pipeline prefix", () => {
    const { result } = setup();
    act(() => result.current.setLastStage("coding"));
    expect(result.current.form.getValues("config.stages")).toEqual([
      "literature",
      "method",
      "coding",
    ]);
  });
});

describe("useNewRunForm estimate", () => {
  it("estimates the options as they are, without the topic", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.estimate.data).toEqual(ESTIMATE));
    expect(estimates()).toEqual([
      {
        method: "POST",
        path: "/api/v1/runs/estimate",
        body: { llm_policy: "auto", budget_cap_usd: null, config: { ...RUN_CONFIG_DEFAULTS } },
      },
    ]);
    expect(result.current.estimate.available).toBe(true);
    expect(result.current.estimate.isUpdating).toBe(false);

    // Typing the topic changes nothing the estimate depends on.
    act(() => result.current.form.setValue("topic", "Monocular depth estimation"));
    expect(result.current.estimate.isUpdating).toBe(false);
  });

  it("asks once for options that settle after several changes", async () => {
    const { result } = setup();
    await waitFor(() => expect(estimates()).toHaveLength(1));
    act(() => {
      result.current.form.setValue("config.max_papers", 30);
      result.current.form.setValue("config.max_papers", 40);
      result.current.form.setValue("budget_cap_usd", "2.50");
    });
    expect(result.current.estimate.isUpdating).toBe(true);
    // The previous figures stay on screen meanwhile.
    expect(result.current.estimate.data).toEqual(ESTIMATE);
    await waitFor(() => expect(estimates()).toHaveLength(2));
    expect(estimates()[1]?.body).toMatchObject({
      budget_cap_usd: "2.50",
      config: { max_papers: 40 },
    });
    await waitFor(() => expect(result.current.estimate.isUpdating).toBe(false));
  });

  it("does not estimate invalid options", async () => {
    const { result } = setup();
    await waitFor(() => expect(estimates()).toHaveLength(1));
    act(() => result.current.form.setValue("budget_cap_usd", "-5"));
    expect(result.current.estimate.available).toBe(false);
    expect(result.current.estimate.data).toBeUndefined();
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(estimates()).toHaveLength(1);
  });
});

describe("useNewRunForm submit", () => {
  async function fillAndSubmit(result: ReturnType<typeof setup>["result"]) {
    act(() => {
      result.current.form.setValue("topic", "  Monocular depth estimation ");
      result.current.form.setValue("llm_policy", "free");
      result.current.form.setValue("config.max_papers", 12);
    });
    await act(async () => {
      await result.current.goTo("budget");
    });
    await act(async () => {
      await result.current.submit();
    });
  }

  it("creates the run with the API's body and hands it over", async () => {
    const onCreated = vi.fn();
    const { result, queryClient } = setup({ onCreated });
    const runsKey = listRunsQueryKey({ path: { project_id: PROJECT } });
    queryClient.setQueryData(runsKey, []);
    queryClient.setQueryData(listRecentRunsQueryKey({ query: { limit: 20 } }), []);

    await fillAndSubmit(result);

    expect(creations()).toEqual([
      {
        method: "POST",
        path: `/api/v1/projects/${PROJECT}/runs`,
        body: {
          topic: "Monocular depth estimation",
          llm_policy: "free",
          budget_cap_usd: null,
          config: { ...RUN_CONFIG_DEFAULTS, max_papers: 12 },
        },
      },
    ]);
    expect(onCreated).toHaveBeenCalledWith(RUN);
    expect(result.current.submitError).toBeNull();
    expect(queryClient.getQueryState(runsKey)?.isInvalidated).toBe(true);
    expect(
      queryClient.getQueryState(listRecentRunsQueryKey({ query: { limit: 20 } }))?.isInvalidated,
    ).toBe(true);
  });

  it("does not send invalid values, and shows the first step with a problem", async () => {
    const { result } = setup();
    act(() => result.current.form.setValue("config.sources", []));
    await act(async () => {
      await result.current.submit();
    });
    expect(creations()).toHaveLength(0);
    expect(result.current.step.id).toBe("topic");
    expect(result.current.stepErrors).toMatchObject({ topic: true, literature: true });
  });

  it("shows the API's validation problems on their fields and step", async () => {
    createResponse = () =>
      json(422, {
        detail: [
          {
            loc: ["body", "config", "max_papers"],
            msg: "Input should be less than or equal to 10",
            type: "less_than_equal",
          },
        ],
      });
    const onCreated = vi.fn();
    const { result } = setup({ onCreated });
    await fillAndSubmit(result);

    expect(result.current.form.formState.errors.config?.max_papers?.message).toBe(
      "maxPapers.outOfRange",
    );
    expect(result.current.step.id).toBe("literature");
    expect(result.current.submitError).toBeNull();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("keeps problems no field explains for the whole form", async () => {
    createResponse = () =>
      json(422, { detail: [{ loc: ["body"], msg: "Field required", type: "missing" }] });
    const { result } = setup();
    await fillAndSubmit(result);
    expect(result.current.submitError?.code).toBe("validation.failed");
    expect(result.current.step.id).toBe("budget");
  });

  it("reports other failures with the API's message code", async () => {
    createResponse = () => json(503, { detail: "orchestrator.unavailable" });
    const onCreated = vi.fn();
    const { result } = setup({ onCreated });
    await fillAndSubmit(result);
    expect(result.current.submitError).toMatchObject({
      code: "orchestrator.unavailable",
      status: 503,
    });
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("starts from an earlier run's options and can reset to them", async () => {
    const { result } = setup({
      defaultValues: { topic: "Again", config: { stages: ["literature"], dataset: null } },
    });
    expect(result.current.form.getValues()).toMatchObject({
      topic: "Again",
      config: { stages: ["literature"], dataset: "" },
    });
    act(() => result.current.form.setValue("topic", "Something else"));
    await act(async () => {
      await result.current.goTo("stages");
    });
    act(() => result.current.reset());
    expect(result.current.form.getValues("topic")).toBe("Again");
    expect(result.current.stepIndex).toBe(0);
  });
});

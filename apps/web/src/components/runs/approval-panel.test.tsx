// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunDetail, StageOutputOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { enMessages as messages } from "@/test/messages";
import { ApprovalPanel } from "./approval-panel";

const output: StageOutputOut = {
  id: "11111111-1111-4111-8111-111111111111",
  version: 2,
  data: { summary: "<img src=x onerror=alert(1)>", papers: 2 },
  sha256: "a".repeat(64),
  model: "fake/research-planner:free",
  degraded: true,
  degraded_reason: "stage.placeholder",
  created_at: "2026-10-30T01:00:00Z",
};

const run: RunDetail = {
  id: "22222222-2222-4222-8222-222222222222",
  project_id: "33333333-3333-4333-8333-333333333333",
  owner_id: "owner",
  topic: "Monocular depth",
  status: "awaiting_approval",
  llm_policy: "auto",
  budget_cap_usd: null,
  error: null,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T01:00:00Z",
  stages: [],
  awaiting: output,
  awaiting_stage: "literature",
  can_steer: true,
};

// The generated client calls fetch(request) with a ready-made Request.
const fetchMock = vi.fn<typeof fetch>();

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPanel(initial: RunDetail) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ui = (value: RunDetail) => (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Asia/Seoul">
        <ApprovalPanel run={value} />
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
  const view = render(ui(initial));
  return { ...view, update: (value: RunDetail) => view.rerender(ui(value)) };
}

const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

beforeEach(() => {
  configureApiClient();
  // Node's Request needs an absolute URL; the browser resolves "/api/v1/..." itself.
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

describe("ApprovalPanel", () => {
  it("shows the output as inert text and warns when it is a degraded placeholder", () => {
    const { container } = renderPanel(run);
    expect(screen.getByText("Placeholder output (degraded)")).toBeTruthy();
    expect(screen.getByText(/this stage is not implemented yet/)).toBeTruthy();
    expect(container.querySelector("code")?.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(container.querySelector("img")).toBeNull();
  });

  it("approves exactly the output id and sha256 that are on screen", async () => {
    fetchMock.mockResolvedValue(respond(202, { status: "accepted" }));
    renderPanel(run);
    fireEvent.click(button("Approve"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe(`/api/v1/runs/${run.id}/approvals`);
    expect(await request.json()).toEqual({
      stage_output_id: output.id,
      sha256: output.sha256,
      decision: "approve",
      comment: "",
    });
  });

  it("asks for a comment before requesting changes", async () => {
    fetchMock.mockResolvedValue(respond(202, { status: "accepted" }));
    renderPanel(run);
    fireEvent.click(button("Request changes"));
    expect(screen.getByText("Say what should change before requesting changes.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Add 2024 papers" } });
    fireEvent.click(button("Request changes"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(await request.json()).toMatchObject({
      decision: "request_changes",
      comment: "Add 2024 papers",
    });
  });

  it("explains a 409 conflict instead of failing silently", async () => {
    fetchMock.mockResolvedValue(respond(409, { detail: "approval.stale" }));
    renderPanel(run);
    fireEvent.click(button("Approve"));
    expect(await screen.findByText("The output changed")).toBeTruthy();
  });

  it("locks the decision buttons when a new version replaces the one being read", () => {
    const view = renderPanel(run);
    view.update({ ...run, awaiting: { ...output, version: 3, sha256: "b".repeat(64) } });
    expect(screen.getByText("A new version arrived")).toBeTruthy();
    expect(button("Approve").disabled).toBe(true);

    fireEvent.click(button("I have read it"));
    expect(button("Approve").disabled).toBe(false);
  });
});

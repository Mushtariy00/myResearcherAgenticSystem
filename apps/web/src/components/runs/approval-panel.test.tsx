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

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock("sonner", () => ({ toast }));

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
  config: {
    year_from: 2018,
    year_to: 2026,
    sources: ["arxiv", "semantic_scholar", "openalex"],
    max_papers: 20,
    stages: ["literature", "method", "coding", "experiment", "writing"],
    dataset: "nyu2",
  },
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
  vi.clearAllMocks();
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
    expect(toast.warning).toHaveBeenCalledWith("This output changed while you were reviewing it.");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("confirms the decision with a toast and clears the comment", async () => {
    fetchMock.mockResolvedValue(respond(202, { status: "accepted" }));
    renderPanel(run);
    const comment = screen.getByLabelText("Comment") as HTMLTextAreaElement;
    fireEvent.change(comment, { target: { value: "Good set of papers" } });
    fireEvent.click(button("Approve"));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Approved. The next stage will start."),
    );
    await waitFor(() => expect(comment.value).toBe(""));
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(await request.json()).toMatchObject({ comment: "Good set of papers" });
  });

  it("shows that the decision is on its way and keeps the buttons locked", async () => {
    let release: (response: Response) => void = () => {};
    fetchMock.mockImplementation(() => new Promise<Response>((resolve) => (release = resolve)));
    renderPanel(run);
    fireEvent.click(button("Approve"));

    const sending = await screen.findByRole("button", { name: "Sending…" });
    expect((sending as HTMLButtonElement).disabled).toBe(true);
    expect(button("Reject").disabled).toBe(true);
    expect(button("Request changes").disabled).toBe(true);

    release(respond(202, { status: "accepted" }));
    expect(await screen.findByRole("button", { name: "Approve" })).toBeTruthy();
    expect(button("Approve").disabled).toBe(false);
  });

  it("moves focus to the comment when changes are requested without one", () => {
    renderPanel(run);
    fireEvent.click(button("Request changes"));
    expect(document.activeElement).toBe(screen.getByLabelText("Comment"));
    expect(screen.getByLabelText("Comment").getAttribute("aria-invalid")).toBe("true");
  });

  it("rejects only after the reviewer confirms", async () => {
    fetchMock.mockResolvedValue(respond(202, { status: "accepted" }));
    renderPanel(run);
    fireEvent.click(button("Reject"));
    fireEvent.click(await screen.findByRole("button", { name: "Keep reviewing" }));
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(button("Reject"));
    fireEvent.click(await screen.findByRole("button", { name: "Reject and stop" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(await request.json()).toMatchObject({ decision: "reject", comment: "" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Rejected. The run will stop."));
  });

  it("reports other failures as an error and keeps the comment", async () => {
    fetchMock.mockResolvedValue(respond(403, { detail: "permission.denied" }));
    renderPanel(run);
    fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Keep me" } });
    fireEvent.click(button("Approve"));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("You do not have permission to do that."),
    );
    expect((screen.getByLabelText("Comment") as HTMLTextAreaElement).value).toBe("Keep me");
    expect(screen.queryByText("The output changed")).toBeNull();
    expect(button("Approve").disabled).toBe(false);
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

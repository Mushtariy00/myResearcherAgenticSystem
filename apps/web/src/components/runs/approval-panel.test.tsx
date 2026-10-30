// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunDetail, StageDetail, StageOutputOut } from "@/client";
import { json, makeQueryClient, mockApi, requestsOf } from "@/hooks/run-hooks.fixtures";
import {
  attemptOut,
  DEMO_METHOD,
  runDetailOut,
  stageDetailOut,
  stageOutputOut,
  stageRunOut,
  versionOut,
} from "@/lib/stage-output.fixtures";
import { enMessages as messages } from "@/test/messages";
import { ApprovalPanel, AwaitingPreview } from "./approval-panel";

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

const run: RunDetail = runDetailOut({
  id: "22222222-2222-4222-8222-222222222222",
  topic: "Monocular depth",
  status: "awaiting_approval",
  stages: [stageRunOut("literature", "output_ready", { outputs: [output] })],
  awaiting: output,
  awaiting_stage: "literature",
  can_steer: true,
});

// A method output waiting after the reviewer sent attempt 1 back.
const methodOutput = stageOutputOut(DEMO_METHOD, { version: 1 });
const methodRun: RunDetail = runDetailOut({
  status: "awaiting_approval",
  stages: [
    stageRunOut("literature", "approved"),
    stageRunOut("method", "output_ready", { attempt: 2, outputs: [methodOutput] }),
  ],
  awaiting: methodOutput,
  awaiting_stage: "method",
});
const sentBack = versionOut(
  { ...DEMO_METHOD, recommended_option: "Lightweight state-space encoder for long-range context" },
  {
    approval: {
      decision: "request_changes",
      comment: "Prefer distillation",
      actor_id: "alice",
      actor_name: "Alice",
      at: "2026-10-30T01:30:00Z",
    },
  },
);
const methodDetail = stageDetailOut(methodRun.id, "method", [
  attemptOut(1, [sentBack], { status: "changes_requested" }),
  attemptOut(2, [versionOut(DEMO_METHOD, { id: methodOutput.id, sha256: methodOutput.sha256 })], {
    feedback: "Prefer distillation",
  }),
]);

type Answer = () => Response | Promise<Response>;
let decide: Answer = () => json(202, { status: "accepted" });
let stageDetail: StageDetail | null = null;
let fetchMock: ReturnType<typeof mockApi>;

beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  decide = () => json(202, { status: "accepted" });
  stageDetail = null;
  fetchMock = mockApi((request, path) => {
    if (request.method === "POST" && path.endsWith("/approvals")) {
      return decide();
    }
    if (request.method === "GET" && path.includes("/stages/") && stageDetail) {
      return json(200, stageDetail);
    }
    return json(404, { detail: "stage.not_found" });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPanel(initial: RunDetail, { readOnly = false } = {}) {
  const queryClient = makeQueryClient();
  const Panel = readOnly ? AwaitingPreview : ApprovalPanel;
  const ui = (value: RunDetail) => (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Asia/Seoul">
        <Panel run={value} />
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
  const view = render(ui(initial));
  return { ...view, update: (value: RunDetail) => view.rerender(ui(value)) };
}

const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

/** The decisions sent, as the JSON bodies of the POSTs. */
async function decisions(count = 1): Promise<unknown[]> {
  const posts = () =>
    fetchMock.mock.calls
      .map(([input]) => input as Request)
      .filter((request) => request.method === "POST");
  await waitFor(() => expect(posts()).toHaveLength(count));
  return Promise.all(posts().map((request) => request.clone().json()));
}

describe("ApprovalPanel", () => {
  it("shows the output as inert text and warns when it is a degraded placeholder", () => {
    const { container } = renderPanel(run);
    expect(screen.getByText("Placeholder output (degraded)")).toBeTruthy();
    expect(screen.getByText(/this stage is not implemented yet/)).toBeTruthy();
    // Not literature-shaped, so the preview falls back to JSON.
    expect(
      screen.getByText("This output does not have the shape of a Literature output"),
    ).toBeTruthy();
    expect(container.querySelector("code")?.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(container.querySelector("img")).toBeNull();
  });

  it("approves exactly the output id and sha256 that are on screen", async () => {
    renderPanel(run);
    fireEvent.click(button("Approve"));
    expect(await decisions()).toEqual([
      { stage_output_id: output.id, sha256: output.sha256, decision: "approve", comment: "" },
    ]);
    expect(requestsOf(fetchMock)).toContain(`POST /api/v1/runs/${run.id}/approvals`);
  });

  it("asks for a comment before requesting changes", async () => {
    renderPanel(run);
    fireEvent.click(button("Request changes"));
    expect(screen.getByText("Say what should change before requesting changes.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Add 2024 papers" } });
    fireEvent.click(button("Request changes"));
    expect(await decisions()).toEqual([
      expect.objectContaining({ decision: "request_changes", comment: "Add 2024 papers" }),
    ]);
  });

  it("explains a 409 conflict instead of failing silently", async () => {
    decide = () => json(409, { detail: "approval.stale" });
    renderPanel(run);
    fireEvent.click(button("Approve"));
    expect(await screen.findByText("The output changed")).toBeTruthy();
    expect(toast.warning).toHaveBeenCalledWith("This output changed while you were reviewing it.");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("confirms the decision with a toast and clears the comment", async () => {
    renderPanel(run);
    const comment = screen.getByLabelText("Comment") as HTMLTextAreaElement;
    fireEvent.change(comment, { target: { value: "Good set of papers" } });
    fireEvent.click(button("Approve"));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Approved. The next stage will start."),
    );
    await waitFor(() => expect(comment.value).toBe(""));
    expect(await decisions()).toEqual([expect.objectContaining({ comment: "Good set of papers" })]);
  });

  it("shows that the decision is on its way and keeps the buttons locked", async () => {
    let release: (response: Response) => void = () => {};
    decide = () => new Promise<Response>((resolve) => (release = resolve));
    renderPanel(run);
    fireEvent.click(button("Approve"));

    const sending = await screen.findByRole("button", { name: "Sending…" });
    expect((sending as HTMLButtonElement).disabled).toBe(true);
    expect(button("Reject").disabled).toBe(true);
    expect(button("Request changes").disabled).toBe(true);

    release(json(202, { status: "accepted" }));
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
    renderPanel(run);
    fireEvent.click(button("Reject"));
    fireEvent.click(await screen.findByRole("button", { name: "Keep reviewing" }));
    expect(requestsOf(fetchMock).filter((request) => request.startsWith("POST"))).toEqual([]);

    fireEvent.click(button("Reject"));
    fireEvent.click(await screen.findByRole("button", { name: "Reject and stop" }));
    expect(await decisions()).toEqual([expect.objectContaining({ decision: "reject" })]);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Rejected. The run will stop."));
  });

  it("reports other failures as an error and keeps the comment", async () => {
    decide = () => json(403, { detail: "permission.denied" });
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

  it("previews the output with its stage view and the changes since the attempt before", async () => {
    stageDetail = methodDetail;
    renderPanel(methodRun);
    expect(screen.getByRole("heading", { name: "Review the Method output" })).toBeTruthy();
    // Demo data gets the Demo notice, not the degraded warning.
    expect(screen.getByText("Demo output")).toBeTruthy();
    expect(screen.queryByText("Placeholder output (degraded)")).toBeNull();
    expect(screen.getByRole("heading", { name: "Research gaps" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: DEMO_METHOD.recommended_option })).toBeTruthy();
    expect(await screen.findByText("Prefer distillation")).toBeTruthy();

    fireEvent.click(await screen.findByRole("tab", { name: "Changes" }));
    expect(screen.getByText("Changes since attempt 1")).toBeTruthy();
    const diff = screen.getByRole("region", { name: "Changes since attempt 1" });
    expect(diff.querySelector("del")?.textContent).toContain("Lightweight state-space encoder");
    expect(diff.querySelector("ins")?.textContent).toContain(DEMO_METHOD.recommended_option);
  });

  it("approves with edits and says which field the stage's schema refused (422)", async () => {
    decide = () =>
      json(422, {
        detail: "decision.invalid_edit",
        loc: ["proposals", 0, "risk"],
        type: "string_too_short",
      });
    renderPanel(methodRun);
    fireEvent.click(screen.getByRole("tab", { name: "Edit before approving" }));
    const approveEdited = button("Approve with edits");
    expect(approveEdited.disabled).toBe(true);
    expect(screen.getByText("No changes yet.")).toBeTruthy();

    const editor = screen.getByRole("textbox", { name: "Edited Method output (JSON)" });
    fireEvent.change(editor, { target: { value: "{ not json" } });
    expect(button("Approve with edits").disabled).toBe(true);

    const edited = {
      ...DEMO_METHOD,
      proposals: DEMO_METHOD.proposals.map((proposal, index) =>
        index === 0 ? { ...proposal, risk: "" } : proposal,
      ),
    };
    fireEvent.change(editor, { target: { value: JSON.stringify(edited, null, 2) } });
    expect(screen.getByRole("region", { name: "Your changes" })).toBeTruthy();
    expect(
      screen.getByText("“Approve” leaves your edits out; “Approve with edits” includes them."),
    ).toBeTruthy();
    fireEvent.click(button("Approve with edits"));

    expect(await decisions()).toEqual([
      {
        stage_output_id: methodOutput.id,
        sha256: methodOutput.sha256,
        decision: "approve",
        comment: "",
        edited_data: edited,
      },
    ]);
    const alert = await screen.findByText("The edit doesn't match the Method format");
    const box = alert.closest('[data-slot="alert"]') as HTMLElement;
    expect(within(box).getByText("proposals[0].risk").tagName).toBe("CODE");
    expect(box.textContent).toContain("the text is too short");
    expect(toast.error).toHaveBeenCalledWith(
      "The edited output doesn't match this stage's format. Check the fields and try again.",
    );
    // The edit stays for the next try.
    expect(
      (screen.getByRole("textbox", { name: "Edited Method output (JSON)" }) as HTMLTextAreaElement)
        .value,
    ).toContain('"risk": ""');
  });

  it("thanks the reviewer for an approval with edits", async () => {
    renderPanel(methodRun);
    fireEvent.click(screen.getByRole("tab", { name: "Edit before approving" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Edited Method output (JSON)" }), {
      target: { value: JSON.stringify({ ...DEMO_METHOD, implementation_focus: "Smaller." }) },
    });
    fireEvent.click(button("Approve with edits"));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Approved with your edits. The next stage will start.",
      ),
    );
  });
});

describe("AwaitingPreview", () => {
  it("shows the same preview read-only, without the editor or decisions", async () => {
    stageDetail = methodDetail;
    renderPanel({ ...methodRun, can_steer: false }, { readOnly: true });
    expect(screen.getByRole("heading", { name: "Method output waiting for review" })).toBeTruthy();
    expect(
      screen.getByText("The run owner or a project owner decides on this output."),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Research gaps" })).toBeTruthy();
    expect(await screen.findByRole("tab", { name: "Changes" })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: "Edit before approving" })).toBeNull();
    for (const name of ["Approve", "Request changes", "Reject"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByLabelText("Comment")).toBeNull();
  });
});

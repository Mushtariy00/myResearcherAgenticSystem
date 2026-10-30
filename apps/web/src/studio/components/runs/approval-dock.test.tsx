// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MethodOutput, RunDetail, StageOutputOut } from "@/client";
import { FakeEventSource, json, runEvent } from "@/hooks/run-hooks.fixtures";
import {
  attemptOut,
  DEMO_LITERATURE,
  DEMO_METHOD,
  runDetailOut,
  stageDetailOut,
  stageOutputOut,
  stageRunOut,
  versionOut,
} from "@/lib/stage-output.fixtures";
import {
  api,
  outputPair,
  RUN_ID,
  renderRunPage,
  sentDecisions,
  setUpRunPage,
  waitForRun,
} from "./run-page.fixtures";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/studio/runs/22222222-2222-4222-8222-222222222222",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock("sonner", () => ({ toast }));
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));
vi.mock("@/components/shared/pdf-viewer", () => ({ PdfViewer: () => null }));

/** Method attempt 1 was sent back; attempt 2 (recommending another proposal) waits for review. */
const REVISED: MethodOutput = {
  ...DEMO_METHOD,
  recommended_option: DEMO_METHOD.proposals[1]?.name ?? "",
};

let awaiting: StageOutputOut;

function seedAwaitingMethod(overrides: Partial<RunDetail> = {}) {
  const sentBack = versionOut(DEMO_METHOD, {
    approval: {
      decision: "request_changes",
      comment: "Prefer the state-space encoder",
      actor_id: "alice",
      actor_name: "Alice",
      at: "2026-10-30T01:30:00Z",
    },
  });
  const pair = outputPair(REVISED);
  awaiting = pair.output;
  api.run = runDetailOut({
    status: "awaiting_approval",
    stages: [
      stageRunOut("literature", "approved", { outputs: [stageOutputOut(DEMO_LITERATURE)] }),
      stageRunOut("method", "output_ready", { attempt: 2, outputs: [awaiting] }),
    ],
    awaiting,
    awaiting_stage: "method",
    ...overrides,
  });
  api.stages.method = stageDetailOut(RUN_ID, "method", [
    attemptOut(1, [sentBack], { status: "changes_requested" }),
    attemptOut(2, [pair.version], { feedback: "Prefer the state-space encoder" }),
  ]);
}

async function openDock() {
  renderRunPage();
  await waitForRun();
  return screen.findByRole("region", { name: "Review the Method output" });
}

beforeEach(() => {
  setUpRunPage();
  seedAwaitingMethod();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ApprovalDock", () => {
  it("names the version under review and docks to the bottom of the screen on phones", async () => {
    const dock = await openDock();
    expect(within(dock).getByText("Version 1")).toBeTruthy();
    expect(within(dock).getByRole("button", { name: "Demo" })).toBeTruthy();
    expect(dock.className).toMatch(/(^|\s)fixed(\s|$)/);
    expect(dock.className).toMatch(/(^|\s)bottom-0(\s|$)/);
    expect(dock.className).toMatch(/(^|\s)md:sticky(\s|$)/);
  });

  it("approves exactly the version on screen", async () => {
    const dock = await openDock();
    fireEvent.click(within(dock).getByRole("button", { name: "Approve" }));
    await waitFor(async () =>
      expect(await sentDecisions()).toEqual([
        {
          stage_output_id: awaiting.id,
          sha256: awaiting.sha256,
          decision: "approve",
          comment: "",
        },
      ]),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Approved. The next stage will start."),
    );
  });

  it("asks for a comment before requesting changes, and focuses it", async () => {
    const dock = await openDock();
    const requestChanges = within(dock).getByRole("button", { name: "Request changes" });
    fireEvent.click(requestChanges);
    const comment = within(dock).getByLabelText("Comment") as HTMLTextAreaElement;
    expect(document.activeElement).toBe(comment);
    expect(comment.getAttribute("aria-invalid")).toBe("true");
    expect(
      within(dock).getByText("Say what should change before requesting changes."),
    ).toBeTruthy();
    expect(await sentDecisions()).toEqual([]);

    fireEvent.change(comment, { target: { value: "Compare with the 2024 baselines" } });
    expect(comment.getAttribute("aria-invalid")).toBeNull();
    fireEvent.click(requestChanges);
    await waitFor(async () =>
      expect(await sentDecisions()).toEqual([
        expect.objectContaining({
          decision: "request_changes",
          comment: "Compare with the 2024 baselines",
        }),
      ]),
    );
  });

  it("approves with edits, and shows where the stage's schema refused them (422)", async () => {
    api.decide = () =>
      json(422, {
        detail: "decision.invalid_edit",
        loc: ["proposals", 0, "risk"],
        type: "string_too_short",
      });
    const dock = await openDock();
    fireEvent.click(within(dock).getByRole("button", { name: "Edit" }));
    const editor = await within(dock).findByRole("textbox", { name: "Method output (JSON)" });
    expect(within(dock).getByRole("button", { name: "Approve" })).toBeTruthy();

    const [first, ...rest] = REVISED.proposals;
    const edited = { ...REVISED, proposals: [{ ...first, risk: "" }, ...rest] };
    fireEvent.change(editor, { target: { value: JSON.stringify(edited, null, 2) } });
    expect(within(dock).getByText("Edited")).toBeTruthy();
    fireEvent.click(within(dock).getByRole("button", { name: "Approve with edits" }));

    await waitFor(async () =>
      expect(await sentDecisions()).toEqual([
        {
          stage_output_id: awaiting.id,
          sha256: awaiting.sha256,
          decision: "approve",
          comment: "",
          edited_data: edited,
        },
      ]),
    );
    const alert = await within(dock).findByRole("alert");
    expect(alert.textContent).toContain(
      "The edited output doesn't match this stage's format. Check the fields and try again.",
    );
    expect(within(alert).getByText("proposals › 0 › risk")).toBeTruthy();
    expect(alert.textContent).toContain("This value is too short.");
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("refuses to approve broken JSON until it is fixed or discarded", async () => {
    const dock = await openDock();
    fireEvent.click(within(dock).getByRole("button", { name: "Edit" }));
    const editor = await within(dock).findByRole("textbox", { name: "Method output (JSON)" });
    fireEvent.change(editor, { target: { value: '{"research_gaps": [' } });
    expect(
      within(dock).getByText("Fix the JSON, or discard your edits, before approving."),
    ).toBeTruthy();
    const approve = within(dock).getByRole("button", { name: "Approve" }) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);

    fireEvent.click(within(dock).getByRole("button", { name: "Discard edits" }));
    expect(approve.disabled).toBe(false);
  });

  it("shows the changes since the attempt the reviewer sent back", async () => {
    const dock = await openDock();
    fireEvent.click(within(dock).getByRole("button", { name: "Changes" }));
    expect(
      await within(dock).findByRole("heading", { name: "Changes since attempt 1" }),
    ).toBeTruthy();
    const diff = within(dock).getByRole("region", { name: "Changes since attempt 1" });
    expect(diff.querySelector("del")?.textContent).toContain(DEMO_METHOD.recommended_option);
    expect(diff.querySelector("ins")?.textContent).toContain(REVISED.recommended_option);
  });

  it("rejects only after the reviewer confirms", async () => {
    const dock = await openDock();
    fireEvent.click(within(dock).getByRole("button", { name: "Reject" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Reject this output?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Keep reviewing" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(await sentDecisions()).toEqual([]);

    fireEvent.click(within(dock).getByRole("button", { name: "Reject" }));
    const again = await screen.findByRole("alertdialog", { name: "Reject this output?" });
    fireEvent.click(within(again).getByRole("button", { name: "Reject and stop" }));
    await waitFor(async () =>
      expect(await sentDecisions()).toEqual([expect.objectContaining({ decision: "reject" })]),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Rejected. The run will stop."));
  });

  it("explains a 409 conflict instead of failing silently", async () => {
    api.decide = () => json(409, { detail: "approval.stale" });
    const dock = await openDock();
    fireEvent.click(within(dock).getByRole("button", { name: "Approve" }));
    expect(await within(dock).findByText("The output changed")).toBeTruthy();
    expect(toast.warning).toHaveBeenCalledWith("This output changed while you were reviewing it.");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("locks the decisions when a new version replaces the one being read", async () => {
    const dock = await openDock();
    const newer = outputPair(
      { ...REVISED, implementation_focus: "A smaller student." },
      {
        version: 2,
      },
    );
    api.run = { ...api.run, awaiting: newer.output };
    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().send(
        runEvent("stage.output_ready", { stage: "method", attempt: 2, degraded: true }),
      );
    });
    expect(await within(dock).findByText("A new version arrived")).toBeTruthy();
    const approve = within(dock).getByRole("button", { name: "Approve" }) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);

    fireEvent.click(within(dock).getByRole("button", { name: "I have read it" }));
    expect(approve.disabled).toBe(false);
    expect(within(dock).getByText("Version 2")).toBeTruthy();
  });

  it("is not offered to people who may only follow the run", async () => {
    seedAwaitingMethod({ can_steer: false });
    renderRunPage();
    await waitForRun();
    expect(
      await screen.findByRole("heading", { name: "Method output waiting for review" }),
    ).toBeTruthy();
    expect(
      screen.getByText("The run owner or a project owner decides on this output."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });
});

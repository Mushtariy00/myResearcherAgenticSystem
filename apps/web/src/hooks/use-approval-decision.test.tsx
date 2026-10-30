// @vitest-environment jsdom
import { act, cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunDetail } from "@/client";
import { getRunQueryKey } from "@/client/@tanstack/react-query.gen";
import type { ApiError } from "@/lib/api-error";
import {
  DEMO_METHOD,
  runDetailOut,
  stageOutputOut,
  stageRunOut,
} from "@/lib/stage-output.fixtures";
import { json, mockApi, renderWithQuery, requestsOf } from "./run-hooks.fixtures";
import { type ApprovalCallbacks, useApprovalDecision } from "./use-approval-decision";

const output = stageOutputOut(DEMO_METHOD, { version: 1 });
const run: RunDetail = runDetailOut({
  status: "awaiting_approval",
  stages: [
    stageRunOut("literature", "approved"),
    stageRunOut("method", "output_ready", { outputs: [output] }),
  ],
  awaiting: output,
  awaiting_stage: "method",
});

type Answer = () => Response | Promise<Response>;
let answer: Answer = () => json(202, { status: "accepted" });
let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  answer = () => json(202, { status: "accepted" });
  fetchMock = mockApi(() => answer());
});

afterEach(cleanup);

function renderDecision(initial: RunDetail | null, callbacks: ApprovalCallbacks = {}) {
  const view = renderWithQuery(
    (props: { run: RunDetail | null }) => useApprovalDecision(props.run, callbacks),
    { initialProps: { run: initial } },
  );
  const invalidate = vi.spyOn(view.queryClient, "invalidateQueries");
  return { ...view, invalidate, update: (next: RunDetail | null) => view.rerender({ run: next }) };
}

async function sentBody(index = 0): Promise<unknown> {
  await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(index));
  const request = fetchMock.mock.calls[index]?.[0];
  if (!(request instanceof Request)) {
    throw new Error(`request ${index} was not sent`);
  }
  return request.clone().json();
}

describe("useApprovalDecision", () => {
  it("approves exactly the output on screen and starts afresh afterwards", async () => {
    const onDecided = vi.fn();
    const { result, invalidate } = renderDecision(run, { onDecided });
    expect(result.current).toMatchObject({
      output,
      stage: "method",
      canDecide: true,
      locked: false,
    });

    act(() => result.current.setComment("  Looks right  "));
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.approve();
    });
    expect(outcome).toBe("sent");
    expect(await sentBody()).toEqual({
      stage_output_id: output.id,
      sha256: output.sha256,
      decision: "approve",
      comment: "Looks right",
    });
    expect(requestsOf(fetchMock)).toEqual([`POST /api/v1/runs/${run.id}/approvals`]);

    await waitFor(() => expect(onDecided).toHaveBeenCalledWith("approve", { edited: false }));
    await waitFor(() => expect(result.current.pending).toBe(false));
    expect(result.current.comment).toBe("");
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: getRunQueryKey({ path: { run_id: run.id } }),
    });
  });

  it("is pending (and locked) while the decision is on its way", async () => {
    let release: (response: Response) => void = () => {};
    answer = () => new Promise<Response>((resolve) => (release = resolve));
    const { result } = renderDecision(run);
    act(() => {
      result.current.reject();
    });
    await waitFor(() => expect(result.current.pending).toBe(true));
    expect(result.current).toMatchObject({ pendingDecision: "reject", locked: true });
    let second: string | undefined;
    act(() => {
      second = result.current.approve();
    });
    expect(second).toBe("locked");

    act(() => release(json(202, { status: "accepted" })));
    await waitFor(() => expect(result.current.pending).toBe(false));
    expect(result.current.pendingDecision).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("asks for a comment before requesting changes", async () => {
    const { result } = renderDecision(run);
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.requestChanges();
    });
    expect(outcome).toBe("comment_required");
    expect(result.current.commentMissing).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();

    act(() => result.current.setComment("   "));
    expect(result.current.commentMissing).toBe(true);
    act(() => result.current.setComment("Add the 2024 papers"));
    expect(result.current.commentMissing).toBe(false);
    act(() => {
      result.current.requestChanges();
    });
    expect(await sentBody()).toMatchObject({
      decision: "request_changes",
      comment: "Add the 2024 papers",
    });
  });

  it("approves with edits, sending the corrected output", async () => {
    const onDecided = vi.fn();
    const { result } = renderDecision(run, { onDecided });
    const corrected = { ...DEMO_METHOD, implementation_focus: "A smaller student." };
    act(() => {
      result.current.approveWithEdits(corrected);
    });
    expect(await sentBody()).toEqual({
      stage_output_id: output.id,
      sha256: output.sha256,
      decision: "approve",
      comment: "",
      edited_data: corrected,
    });
    await waitFor(() => expect(onDecided).toHaveBeenCalledWith("approve", { edited: true }));
  });

  it("says where an edit failed the stage's schema (422 decision.invalid_edit)", async () => {
    answer = () =>
      json(422, {
        detail: "decision.invalid_edit",
        loc: ["proposals", 0, "risk"],
        type: "string_too_short",
      });
    const onError = vi.fn<(error: ApiError) => void>();
    const { result } = renderDecision(run, { onError });
    act(() => {
      result.current.approveWithEdits({ ...DEMO_METHOD, proposals: [] });
    });
    await waitFor(() => expect(result.current.invalidEdit).not.toBeNull());
    expect(result.current.invalidEdit).toEqual({
      loc: ["proposals", 0, "risk"],
      type: "string_too_short",
    });
    expect(result.current.error).toMatchObject({ code: "decision.invalid_edit", status: 422 });
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ code: "decision.invalid_edit" });
    expect(result.current.conflict).toBe(false);

    // The next attempt starts without the old error.
    answer = () => json(202, { status: "accepted" });
    act(() => {
      result.current.approveWithEdits(DEMO_METHOD);
    });
    expect(result.current.invalidEdit).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("reports other failures without a conflict", async () => {
    answer = () => json(403, { detail: "permission.denied" });
    const onError = vi.fn<(error: ApiError) => void>();
    const onConflict = vi.fn();
    const { result } = renderDecision(run, { onError, onConflict });
    act(() => result.current.setComment("Keep this"));
    act(() => {
      result.current.approve();
    });
    await waitFor(() => expect(onError).toHaveBeenCalledTimes(1));
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ code: "permission.denied", status: 403 });
    expect(result.current).toMatchObject({
      conflict: false,
      invalidEdit: null,
      comment: "Keep this",
    });
    expect(onConflict).not.toHaveBeenCalled();
  });

  it("turns a 409 into a conflict and refetches the run", async () => {
    answer = () => json(409, { detail: "approval.stale" });
    const onConflict = vi.fn<(error: ApiError) => void>();
    const onError = vi.fn();
    const { result, invalidate } = renderDecision(run, { onConflict, onError });
    act(() => {
      result.current.approve();
    });
    await waitFor(() => expect(result.current.conflict).toBe(true));
    expect(onConflict.mock.calls[0]?.[0]).toMatchObject({ code: "approval.stale", status: 409 });
    expect(onError).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: getRunQueryKey({ path: { run_id: run.id } }),
      }),
    );
  });

  it("locks the decisions when a new version replaces the one being read", () => {
    const { result, update } = renderDecision(run);
    act(() => result.current.setComment("Half-written note"));
    const newer = { ...output, version: 2, sha256: "b".repeat(64) };
    update({ ...run, awaiting: newer });
    expect(result.current).toMatchObject({ updatedWhileOpen: true, locked: true, output: newer });
    // The review goes on: the note stays.
    expect(result.current.comment).toBe("Half-written note");
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.approve();
    });
    expect(outcome).toBe("locked");
    expect(fetchMock).not.toHaveBeenCalled();

    act(() => result.current.acknowledge());
    expect(result.current).toMatchObject({ updatedWhileOpen: false, locked: false });
  });

  it("starts over when another stage's output waits, or none", () => {
    const { result, update } = renderDecision(run);
    act(() => result.current.setComment("About the method"));
    act(() => {
      result.current.requestChanges();
    });
    const coding = stageOutputOut({ summary: "x" }, { version: 1 });
    update({ ...run, awaiting: coding, awaiting_stage: "coding" });
    expect(result.current).toMatchObject({
      stage: "coding",
      output: coding,
      comment: "",
      updatedWhileOpen: false,
      locked: false,
    });

    update({ ...run, status: "running", awaiting: null, awaiting_stage: null });
    expect(result.current).toMatchObject({ output: null, stage: null, canDecide: false });
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.approve();
    });
    expect(outcome).toBe("no_output");
  });

  it("refuses decisions from people who may only look", () => {
    const { result } = renderDecision({ ...run, can_steer: false });
    expect(result.current.canDecide).toBe(false);
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.approve();
    });
    expect(outcome).toBe("not_allowed");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("has nothing to decide before the run loads", () => {
    const { result } = renderDecision(null);
    expect(result.current).toMatchObject({ output: null, stage: null, canDecide: false });
    expect(result.current.reject()).toBe("no_output");
  });
});

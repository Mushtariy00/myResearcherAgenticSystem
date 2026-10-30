// @vitest-environment jsdom
import { act, cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { StageDetail } from "@/client";
import { attemptOut, DEMO_METHOD, stageDetailOut, versionOut } from "@/lib/stage-output.fixtures";
import { json, mockApi, renderWithQuery, requestsOf } from "./run-hooks.fixtures";
import { type UseStageOptions, useStage } from "./use-stage";

const RUN_ID = "22222222-2222-4222-8222-222222222222";

// Attempt 1 was sent back with a comment; attempt 2 has the new output and a reviewer's edit.
const sentBack = versionOut(DEMO_METHOD, {
  approval: {
    decision: "request_changes",
    comment: "Cite the 2024 papers",
    actor_id: "alice",
    actor_name: "Alice",
    at: "2026-10-30T01:30:00Z",
  },
});
const second = versionOut({ ...DEMO_METHOD, recommended_option: DEMO_METHOD.proposals[1]?.name });
const edited = versionOut(
  { ...second.data, implementation_focus: "A smaller student." },
  { version: 2, edited_by: "bob", edited_by_name: "Bob", degraded: false, degraded_reason: null },
);
const attempt1 = attemptOut(1, [sentBack], { status: "changes_requested" });
const attempt2 = attemptOut(2, [second, edited], { feedback: "Cite the 2024 papers" });
const methodDetail = stageDetailOut(RUN_ID, "method", [attempt1, attempt2]);

let detail: StageDetail = methodDetail;
let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  detail = methodDetail;
  fetchMock = mockApi((_request, path) =>
    path === `/api/v1/runs/${RUN_ID}/stages/method`
      ? json(200, detail)
      : json(404, { detail: "stage.not_found" }),
  );
});

afterEach(cleanup);

function renderStage(stage: string | null, options: UseStageOptions = {}) {
  return renderWithQuery(
    (props: { stage: string | null; options: UseStageOptions }) =>
      useStage(RUN_ID, props.stage, props.options),
    { initialProps: { stage, options } },
  );
}

describe("useStage", () => {
  it("shows the newest version and diffs it against the one before", async () => {
    const { result } = renderStage("method");
    await waitFor(() => expect(result.current.detail).toEqual(methodDetail));
    const view = result.current;

    expect(view.attempts.map((attempt) => attempt.attempt)).toEqual([1, 2]);
    expect(view.currentAttempt?.id).toBe(attempt2.id);
    expect(view.versions.map((ref) => ref.output.id)).toEqual([sentBack.id, second.id, edited.id]);
    expect(view.current?.output.id).toBe(edited.id);
    expect(view.selected?.output.id).toBe(edited.id);
    expect(view.followingLatest).toBe(true);
    expect(view.previous).toMatchObject({ relation: "version", output: { id: second.id } });
    expect(view.narrowed).toMatchObject({ kind: "method", data: edited.data });
    expect(view.previousNarrowed).toMatchObject({ kind: "method", data: second.data });
    expect(view.summary).toEqual({
      kind: "method",
      proposals: 3,
      recommended: DEMO_METHOD.proposals[1]?.name,
    });
    expect(view.isDemo).toBe(false);
    expect(view.live).toBe(true);
    expect(requestsOf(fetchMock)).toEqual([`GET /api/v1/runs/${RUN_ID}/stages/method`]);
  });

  it("selects an older version, and follows the newest again", async () => {
    const { result } = renderStage("method");
    await waitFor(() => expect(result.current.detail).toBeDefined());

    act(() => result.current.select(second.id));
    expect(result.current.selected?.output.id).toBe(second.id);
    expect(result.current.followingLatest).toBe(false);
    expect(result.current.previous).toMatchObject({
      relation: "attempt",
      output: { id: sentBack.id },
      attempt: { attempt: 1 },
    });
    expect(result.current.isDemo).toBe(true);

    act(() => result.current.select(sentBack.id));
    expect(result.current.previous).toBeUndefined();

    act(() => result.current.select(null));
    expect(result.current.selected?.output.id).toBe(edited.id);
    expect(result.current.followingLatest).toBe(true);
  });

  it("shows the version it is told to, such as the output under review", async () => {
    const { result, rerender } = renderStage("method", { outputId: second.id });
    await waitFor(() => expect(result.current.selected?.output.id).toBe(second.id));
    // select() cannot override a version the caller controls.
    act(() => result.current.select(edited.id));
    expect(result.current.selected?.output.id).toBe(second.id);

    // An id the detail does not list yet shows nothing rather than another version.
    rerender({ stage: "method", options: { outputId: "not-listed-yet" } });
    expect(result.current.selected).toBeUndefined();
    expect(result.current.narrowed).toBeNull();
    expect(result.current.current?.output.id).toBe(edited.id);
  });

  it("falls back to raw JSON for versions that fail the stage's schema", async () => {
    const legacy = versionOut({ summary: "placeholder" }, { schema_ok: false });
    detail = stageDetailOut(RUN_ID, "method", [attemptOut(1, [legacy], { status: "approved" })]);
    const { result } = renderStage("method");
    await waitFor(() => expect(result.current.detail).toBeDefined());
    expect(result.current.narrowed).toEqual({
      kind: "raw",
      stage: "method",
      data: { summary: "placeholder" },
      reason: "schema_failed",
    });
    expect(result.current.summary).toEqual({
      kind: "raw",
      stage: "method",
      reason: "schema_failed",
    });
    expect(result.current.live).toBe(false);
  });

  it("waits for a stage before asking for it", () => {
    const { result } = renderStage(null);
    expect(result.current.query.fetchStatus).toBe("idle");
    expect(result.current).toMatchObject({
      detail: undefined,
      selected: undefined,
      narrowed: null,
      summary: null,
      live: false,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("follows the newest version again when it moves to another stage", async () => {
    const { result, rerender } = renderStage("method");
    await waitFor(() => expect(result.current.detail).toBeDefined());
    act(() => result.current.select(sentBack.id));
    expect(result.current.followingLatest).toBe(false);

    rerender({ stage: "coding", options: {} });
    expect(result.current.followingLatest).toBe(true);
    expect(result.current.detail).toBeUndefined();
  });
});

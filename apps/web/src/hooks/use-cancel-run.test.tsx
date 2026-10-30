// @vitest-environment jsdom
import { act, cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiError } from "@/lib/api-error";
import { json, mockApi, renderWithQuery, requestsOf } from "./run-hooks.fixtures";
import { type CancelRunCallbacks, useCancelRun } from "./use-cancel-run";

const RUN_ID = "22222222-2222-4222-8222-222222222222";

let answer: () => Response = () => json(202, { status: "accepted" });
let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  answer = () => json(202, { status: "accepted" });
  fetchMock = mockApi(() => answer());
});

afterEach(cleanup);

function renderCancel(callbacks: CancelRunCallbacks = {}) {
  const view = renderWithQuery(() => useCancelRun(callbacks));
  return { ...view, invalidate: vi.spyOn(view.queryClient, "invalidateQueries") };
}

describe("useCancelRun", () => {
  it("cancels the run and refetches it, its stages and the GPU queue", async () => {
    const onCancelled = vi.fn();
    const { result, invalidate } = renderCancel({ onCancelled });
    act(() => result.current.cancel(RUN_ID));
    await waitFor(() => expect(onCancelled).toHaveBeenCalledWith(RUN_ID));
    expect(requestsOf(fetchMock)).toEqual([`POST /api/v1/runs/${RUN_ID}/cancel`]);
    await waitFor(() => expect(result.current.pending).toBe(false));
    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey?.[0]);
    expect(keys).toContainEqual(
      expect.objectContaining({ _id: "getRun", path: { run_id: RUN_ID } }),
    );
    expect(keys).toContainEqual({ _id: "getStage", path: { run_id: RUN_ID } });
    expect(keys).toContainEqual({ _id: "getGpuQueue" });
    expect(result.current).toMatchObject({ error: null, alreadyFinished: false });
  });

  it("treats an already finished run as nothing to cancel, not a failure", async () => {
    answer = () => json(409, { detail: "run.already_finished" });
    const onAlreadyFinished = vi.fn();
    const onError = vi.fn();
    const { result } = renderCancel({ onAlreadyFinished, onError });
    act(() => result.current.cancel(RUN_ID));
    await waitFor(() => expect(onAlreadyFinished).toHaveBeenCalledTimes(1));
    expect(onAlreadyFinished.mock.calls[0]).toEqual([
      RUN_ID,
      expect.objectContaining({ code: "run.already_finished", status: 409 }),
    ]);
    expect(onError).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.alreadyFinished).toBe(true));
  });

  it("reports failures, and an already finished run without its own callback", async () => {
    const onError = vi.fn<(error: ApiError, runId: string) => void>();
    const { result } = renderCancel({ onError });
    answer = () => json(503, { detail: "orchestrator.unavailable" });
    act(() => result.current.cancel(RUN_ID));
    await waitFor(() => expect(onError).toHaveBeenCalledTimes(1));
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ code: "orchestrator.unavailable" });

    answer = () => json(409, { detail: "run.already_finished" });
    act(() => result.current.cancel(RUN_ID));
    await waitFor(() => expect(onError).toHaveBeenCalledTimes(2));
    expect(onError.mock.calls[1]?.[0]).toMatchObject({ code: "run.already_finished" });
  });

  it("tells which run is being cancelled", async () => {
    let release: (response: Response) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => (release = resolve)));
    const { result } = renderCancel();
    act(() => result.current.cancel(RUN_ID));
    await waitFor(() => expect(result.current.pendingRunId).toBe(RUN_ID));
    act(() => release(json(202, { status: "accepted" })));
    await waitFor(() => expect(result.current.pendingRunId).toBeNull());
  });
});

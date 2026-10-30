// @vitest-environment jsdom
import { act, cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiError } from "@/lib/api-error";
import { json, mockApi, renderWithQuery, requestsOf } from "./run-hooks.fixtures";
import { type RetryRunCallbacks, useRetryRun } from "./use-retry-run";

const RUN_ID = "22222222-2222-4222-8222-222222222222";

let answer: () => Response | Promise<Response> = () => json(202, { status: "accepted" });
let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  answer = () => json(202, { status: "accepted" });
  fetchMock = mockApi(() => answer());
});

afterEach(cleanup);

function renderRetry(callbacks: RetryRunCallbacks = {}) {
  const view = renderWithQuery(() => useRetryRun(callbacks));
  return { ...view, invalidate: vi.spyOn(view.queryClient, "invalidateQueries") };
}

/** The partial query keys invalidated so far (their first element). */
function invalidatedKeys(spy: ReturnType<typeof renderRetry>["invalidate"]): unknown[] {
  return spy.mock.calls.map(([filters]) => filters?.queryKey?.[0]);
}

describe("useRetryRun", () => {
  it("retries from the given stage and refetches what shows the run", async () => {
    const onRetried = vi.fn();
    const { result, invalidate } = renderRetry({ onRetried });
    act(() => result.current.retry(RUN_ID, "method"));
    await waitFor(() => expect(onRetried).toHaveBeenCalledWith(RUN_ID, "method"));
    expect(requestsOf(fetchMock)).toEqual([`POST /api/v1/runs/${RUN_ID}/retry?stage=method`]);

    await waitFor(() => expect(result.current.pending).toBe(false));
    const keys = invalidatedKeys(invalidate);
    expect(keys).toContainEqual(
      expect.objectContaining({ _id: "getRun", path: { run_id: RUN_ID } }),
    );
    expect(keys).toContainEqual({ _id: "getStage", path: { run_id: RUN_ID } });
    expect(keys).toContainEqual(
      expect.objectContaining({ _id: "listRunArtifacts", path: { run_id: RUN_ID } }),
    );
    expect(keys).toContainEqual({ _id: "listRuns" });
    expect(keys).toContainEqual({ _id: "listRecentRuns" });
    expect(keys).not.toContainEqual({ _id: "getGpuQueue" });
  });

  it("tells which run and stage are being retried", async () => {
    let release: (response: Response) => void = () => {};
    answer = () => new Promise<Response>((resolve) => (release = resolve));
    const { result } = renderRetry();
    act(() => result.current.retry(RUN_ID, "coding"));
    await waitFor(() => expect(result.current.pending).toBe(true));
    expect(result.current).toMatchObject({ pendingRunId: RUN_ID, pendingStage: "coding" });
    act(() => release(json(202, { status: "accepted" })));
    await waitFor(() => expect(result.current.pending).toBe(false));
    expect(result.current).toMatchObject({ pendingRunId: null, pendingStage: null, error: null });
  });

  it("reports a refused retry with its message code", async () => {
    answer = () => json(409, { detail: "run.not_retryable" });
    const onError = vi.fn<(error: ApiError, runId: string, stage: string) => void>();
    const { result } = renderRetry({ onError });
    act(() => result.current.retry(RUN_ID, "literature"));
    await waitFor(() => expect(onError).toHaveBeenCalledTimes(1));
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ code: "run.not_retryable", status: 409 });
    expect(onError.mock.calls[0]?.slice(1)).toEqual([RUN_ID, "literature"]);
    await waitFor(() => expect(result.current.error?.code).toBe("run.not_retryable"));

    act(() => result.current.reset());
    await waitFor(() => expect(result.current.error).toBeNull());
  });

  it("rejects retryAsync with the ApiError", async () => {
    answer = () => json(409, { detail: "stage.not_reached" });
    const { result } = renderRetry();
    await expect(result.current.retryAsync(RUN_ID, "writing")).rejects.toMatchObject({
      code: "stage.not_reached",
    });
  });
});

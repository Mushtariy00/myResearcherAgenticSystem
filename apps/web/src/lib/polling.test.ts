// @vitest-environment jsdom
import { focusManager, QueryClient, QueryObserver } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api-error";
import { isPageVisible, type PolledQuery, pollInterval, pollWhileVisible } from "./polling";

const ok: PolledQuery = { state: { status: "success", error: null } };
const failed = (error: unknown): PolledQuery => ({ state: { status: "error", error } });

describe("pollInterval", () => {
  it("polls at the interval while the page is visible", () => {
    expect(pollInterval(5_000, ok, {}, true)).toBe(5_000);
    expect(pollInterval(5_000, { state: { status: "pending", error: null } }, {}, true)).toBe(
      5_000,
    );
  });

  it("pauses while the page is hidden", () => {
    expect(pollInterval(5_000, ok, {}, false)).toBe(false);
    expect(pollInterval(5_000, failed(new ApiError("server.error", 503)), {}, false)).toBe(false);
  });

  it("slows down after failures that may go away", () => {
    expect(pollInterval(5_000, failed(new ApiError("server.error", 503)), {}, true)).toBe(30_000);
    expect(pollInterval(20_000, failed(new ApiError("network.error")), {}, true)).toBe(60_000);
    expect(pollInterval(60_000, failed(new TypeError("Failed to fetch")), {}, true)).toBe(120_000);
    expect(
      pollInterval(5_000, failed(new ApiError("unknown", 429)), { errorIntervalMs: 9_000 }, true),
    ).toBe(9_000);
  });

  it("stops after client errors, which asking again will not fix", () => {
    for (const status of [401, 403, 404, 422]) {
      expect(
        pollInterval(5_000, failed(new ApiError("unknown", status)), {}, true),
        String(status),
      ).toBe(false);
    }
  });

  it("reads visibility from TanStack Query's focus state", () => {
    focusManager.setFocused(false);
    expect(isPageVisible()).toBe(false);
    focusManager.setFocused(true);
    expect(isPageVisible()).toBe(true);
    focusManager.setFocused(undefined);
  });
});

describe("pollWhileVisible", () => {
  let visibility: DocumentVisibilityState = "visible";

  function setVisibility(next: DocumentVisibilityState) {
    visibility = next;
    // TanStack Query's focus manager listens for this on window.
    window.dispatchEvent(new Event("visibilitychange"));
  }

  beforeEach(() => {
    visibility = "visible";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibility,
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function poll(queryFn: () => Promise<string>, intervalMs = 1_000) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.mount();
    const observer = new QueryObserver(queryClient, {
      queryKey: ["polled"],
      queryFn,
      ...pollWhileVisible(intervalMs),
    });
    const unsubscribe = observer.subscribe(() => {});
    const stop = () => {
      unsubscribe();
      queryClient.unmount();
      queryClient.clear();
    };
    return { queryClient, stop };
  }

  it("asks again every interval only while the page is visible", async () => {
    const queryFn = vi.fn(async () => "ok");
    const { stop } = poll(queryFn);
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(queryFn).toHaveBeenCalledTimes(3);

    setVisibility("hidden");
    await vi.advanceTimersByTimeAsync(30_000);
    expect(queryFn).toHaveBeenCalledTimes(3);

    // Coming back refreshes at once, then polling resumes.
    setVisibility("visible");
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(4);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(queryFn).toHaveBeenCalledTimes(5);
    stop();
  });

  it("keeps the timer off when the data changes while the page is hidden", async () => {
    const queryFn = vi.fn(async () => "ok");
    const { queryClient, stop } = poll(queryFn);
    await vi.advanceTimersByTimeAsync(0);
    setVisibility("hidden");
    // Something else refreshes the query in the background (e.g. a mutation invalidates it).
    await queryClient.invalidateQueries({ queryKey: ["polled"] });
    expect(queryFn).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(queryFn).toHaveBeenCalledTimes(2);

    setVisibility("visible");
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(queryFn).toHaveBeenCalledTimes(4);
    stop();
  });

  it("stops polling after a client error", async () => {
    const queryFn = vi.fn(async (): Promise<string> => {
      throw new ApiError("permission.denied", 403);
    });
    const { stop } = poll(queryFn);
    await vi.advanceTimersByTimeAsync(0);
    expect(queryFn).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(queryFn).toHaveBeenCalledTimes(1);
    stop();
  });

  it("polls more slowly after a server error, and normally once it recovers", async () => {
    let fail = true;
    const queryFn = vi.fn(async () => {
      if (fail) {
        throw new ApiError("server.error", 503);
      }
      return "ok";
    });
    const { stop } = poll(queryFn, 1_000);
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(29_000);
    expect(queryFn).toHaveBeenCalledTimes(1);
    fail = false;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(queryFn).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(queryFn).toHaveBeenCalledTimes(3);
    stop();
  });
});

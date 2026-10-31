// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource, installEventSource, runEvent } from "./run-hooks.fixtures";
import { RECONNECT_DELAYS_MS, useRunEvents } from "./use-run-events";

const RUN_ID = "22222222-2222-4222-8222-222222222222";

beforeEach(() => {
  installEventSource();
  // Only the reconnect timers; animation frames and promises run as usual.
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function follow(canResume: () => Promise<boolean> = async () => true) {
  const check = vi.fn(canResume);
  const view = renderHook(() => useRunEvents(RUN_ID, () => {}, check));
  return { ...view, check };
}

/** Waits `ms` of fake time, and for the resume check that runs then. */
async function wait(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useRunEvents batching", () => {
  it("shows events on a hidden page too, which runs no animation frames", async () => {
    vi.stubGlobal("requestAnimationFrame", () => 1); // a frame that never comes
    vi.stubGlobal("cancelAnimationFrame", () => {});
    const { result } = follow();
    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().send(runEvent("log", { message: "while hidden" }, 7));
    });
    expect(result.current.events).toHaveLength(0); // still batching
    await wait(250);
    expect(result.current.events.map((event) => event.seq)).toEqual([7]);
  });
});

describe("useRunEvents reconnecting", () => {
  it("opens the stream again after the browser gave up, after the newest event it has", async () => {
    const { result, check } = follow();
    const first = FakeEventSource.latest();
    act(() => {
      first.open();
      first.send(runEvent("log", { message: "a" }, 41), runEvent("log", { message: "b" }, 42));
    });
    // Caddy answers 502 while the API restarts: EventSource closes and never retries itself.
    act(() => first.fail());
    expect(result.current.state).toBe("reconnecting");
    expect(FakeEventSource.instances).toHaveLength(1);

    await wait(RECONNECT_DELAYS_MS[0] ?? 0);
    expect(check).toHaveBeenCalledTimes(1);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.latest().url).toBe(`/api/v1/runs/${RUN_ID}/events?after=42`);

    act(() => FakeEventSource.latest().open());
    expect(result.current.state).toBe("live");
  });

  it("leaves retrying to the browser while it reconnects by itself", async () => {
    const { result, check } = follow();
    act(() => FakeEventSource.latest().fail(FakeEventSource.CONNECTING));
    expect(result.current.state).toBe("reconnecting");
    await wait(60_000);
    expect(check).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("waits longer each time, and gives up after the last wait", async () => {
    const { result } = follow();
    for (const delay of RECONNECT_DELAYS_MS) {
      act(() => FakeEventSource.latest().fail());
      expect(result.current.state).toBe("reconnecting");
      const opened = FakeEventSource.instances.length;
      await wait(delay - 1);
      expect(FakeEventSource.instances).toHaveLength(opened);
      await wait(1);
      expect(FakeEventSource.instances).toHaveLength(opened + 1);
    }
    act(() => FakeEventSource.latest().fail());
    expect(result.current.state).toBe("error");
    await wait(120_000);
    expect(FakeEventSource.instances).toHaveLength(RECONNECT_DELAYS_MS.length + 1);

    // Reconnect starts over.
    act(() => result.current.reconnect());
    expect(FakeEventSource.instances).toHaveLength(RECONNECT_DELAYS_MS.length + 2);
    expect(result.current.state).toBe("connecting");
  });

  it("starts the waits over once a connection works again", async () => {
    follow();
    act(() => FakeEventSource.latest().fail());
    await wait(RECONNECT_DELAYS_MS[0] ?? 0);
    act(() => FakeEventSource.latest().open());
    act(() => FakeEventSource.latest().fail());
    await wait(RECONNECT_DELAYS_MS[0] ?? 0);
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it("stops when the session ended or the run is gone (401, 404)", async () => {
    const { result, check } = follow(async () => false);
    act(() => FakeEventSource.latest().fail());
    await wait(RECONNECT_DELAYS_MS[0] ?? 0);
    expect(check).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe("error");
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("keeps trying when the check itself fails (the API is still down)", async () => {
    follow(async () => {
      throw new TypeError("Failed to fetch");
    });
    act(() => FakeEventSource.latest().fail());
    await wait(RECONNECT_DELAYS_MS[0] ?? 0);
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it("stops trying once the page is gone", async () => {
    const { unmount, check } = follow();
    act(() => FakeEventSource.latest().fail());
    unmount();
    await wait(60_000);
    expect(check).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});

describe("useRunEvents after the run ends", () => {
  it("opens the stream again when the finished run starts again (a retry)", () => {
    const { result, rerender } = renderHook(
      ({ going }: { going: boolean }) => useRunEvents(RUN_ID, () => {}, undefined, going),
      { initialProps: { going: true } },
    );
    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().send(runEvent("log", { message: "the last try failed" }, 9));
      FakeEventSource.latest().end();
    });
    // Ended while the run still looked under way: it stays ended.
    expect(result.current.state).toBe("ended");
    rerender({ going: false }); // the run's detail now says it failed
    expect(FakeEventSource.instances).toHaveLength(1);

    rerender({ going: true }); // retried
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.latest().url).toBe(`/api/v1/runs/${RUN_ID}/events?after=9`);
    act(() => FakeEventSource.latest().open());
    expect(result.current.state).toBe("live");
  });
});

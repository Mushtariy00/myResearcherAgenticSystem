"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { affectsRunDetail, mergeEvents, parseRunEvent, type RunEvent } from "@/lib/run-events";

export type StreamState = "connecting" | "live" | "reconnecting" | "ended" | "error";

/** How long to gather stage events before refetching the run detail once. */
const DETAIL_REFRESH_DELAY_MS = 300;

/**
 * The waits before each new connection after the browser gave up on the stream. It gives up on
 * any answer other than 200, such as Caddy's 502 while the API restarts; after the last wait
 * the hook stops trying (the Reconnect button starts over).
 */
export const RECONNECT_DELAYS_MS: readonly number[] = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000];

/**
 * Whether opening the stream again can work. The browser does not say why it gave up, so the
 * caller asks the API: false when the session ended or the run is gone (401, 403, 404).
 */
export type ResumeCheck = () => Promise<boolean>;

/**
 * Follows a run's live events with the browser's EventSource (same origin, so the session cookie
 * goes along; reconnects resend Last-Event-ID). Events are batched per animation frame and
 * de-duplicated by seq. `onDetailChange` fires (debounced) after stage, status and call events.
 *
 * When the browser gives up on the stream, the hook opens a new one after a growing wait
 * (RECONNECT_DELAYS_MS), resuming after the newest event it has, unless `canResume` says the
 * session or the run is gone.
 */
export function useRunEvents(runId: string, onDetailChange: () => void, canResume?: ResumeCheck) {
  const [events, setEvents] = useState<readonly RunEvent[]>([]);
  const [state, setState] = useState<StreamState>("connecting");
  const [attempt, setAttempt] = useState(0);
  const latestSeq = useRef(0);
  const retries = useRef(0);
  const detailCallback = useRef(onDetailChange);
  const resumeCheck = useRef(canResume);

  useEffect(() => {
    detailCallback.current = onDetailChange;
    resumeCheck.current = canResume;
  }, [onDetailChange, canResume]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` restarts the stream on demand
  useEffect(() => {
    let pending: RunEvent[] = [];
    let frame: number | null = null;
    let detailTimer: ReturnType<typeof setTimeout> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const refreshDetail = () => {
      detailTimer ??= setTimeout(() => {
        detailTimer = null;
        detailCallback.current();
      }, DETAIL_REFRESH_DELAY_MS);
    };
    const flush = () => {
      frame = null;
      const batch = pending;
      pending = [];
      setEvents((current) => mergeEvents(current, batch));
    };
    const retryLater = () => {
      const delay = RECONNECT_DELAYS_MS[retries.current];
      if (delay === undefined) {
        setState("error");
        return;
      }
      retries.current += 1;
      setState("reconnecting");
      retryTimer = setTimeout(async () => {
        retryTimer = null;
        // A check that fails (the API is still down) is no reason to stop trying.
        const resumable = await (resumeCheck.current?.() ?? Promise.resolve(true)).catch(
          () => true,
        );
        if (disposed) {
          return;
        }
        if (resumable) {
          setAttempt((value) => value + 1);
        } else {
          setState("error");
        }
      }, delay);
    };

    setState((current) => (current === "reconnecting" ? current : "connecting"));
    // Resume after what we already have; the server replays everything newer.
    const source = new EventSource(
      `/api/v1/runs/${encodeURIComponent(runId)}/events?after=${latestSeq.current}`,
    );
    source.onopen = () => {
      retries.current = 0;
      setState("live");
    };
    source.onmessage = (message: MessageEvent<string>) => {
      const event = parseRunEvent(message.data);
      if (!event) {
        return;
      }
      latestSeq.current = Math.max(latestSeq.current, event.seq);
      pending.push(event);
      frame ??= requestAnimationFrame(flush);
      if (affectsRunDetail(event.type)) {
        refreshDetail();
      }
    };
    // Sent once a finished run has replayed everything; without close() the browser reconnects.
    source.addEventListener("end", () => {
      source.close();
      setState("ended");
      refreshDetail();
    });
    source.onerror = () => {
      // CONNECTING: the browser retries by itself. CLOSED: it gave up, so we try again later.
      if (source.readyState === EventSource.CLOSED) {
        retryLater();
      } else {
        setState("reconnecting");
      }
    };

    return () => {
      disposed = true;
      source.close();
      if (frame !== null) {
        cancelAnimationFrame(frame);
      }
      if (pending.length > 0) {
        const batch = pending;
        setEvents((current) => mergeEvents(current, batch));
      }
      if (detailTimer !== null) {
        clearTimeout(detailTimer);
      }
      if (retryTimer !== null) {
        clearTimeout(retryTimer);
      }
    };
  }, [runId, attempt]);

  const reconnect = useCallback(() => {
    retries.current = 0;
    setAttempt((value) => value + 1);
  }, []);

  return { events, state, reconnect };
}

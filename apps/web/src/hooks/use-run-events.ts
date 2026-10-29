"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { affectsRunDetail, mergeEvents, parseRunEvent, type RunEvent } from "@/lib/run-events";

export type StreamState = "connecting" | "live" | "reconnecting" | "ended" | "error";

/** How long to gather stage events before refetching the run detail once. */
const DETAIL_REFRESH_DELAY_MS = 300;

/**
 * Follows a run's live events with the browser's EventSource (same origin, so the session cookie
 * goes along; reconnects resend Last-Event-ID). Events are batched per animation frame and
 * de-duplicated by seq. `onDetailChange` fires (debounced) after stage and status events.
 */
export function useRunEvents(runId: string, onDetailChange: () => void) {
  const [events, setEvents] = useState<readonly RunEvent[]>([]);
  const [state, setState] = useState<StreamState>("connecting");
  const [attempt, setAttempt] = useState(0);
  const latestSeq = useRef(0);
  const detailCallback = useRef(onDetailChange);

  useEffect(() => {
    detailCallback.current = onDetailChange;
  }, [onDetailChange]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` restarts the stream on demand
  useEffect(() => {
    let pending: RunEvent[] = [];
    let frame: number | null = null;
    let detailTimer: ReturnType<typeof setTimeout> | null = null;

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

    setState("connecting");
    // Resume after what we already have; the server replays everything newer.
    const source = new EventSource(
      `/api/v1/runs/${encodeURIComponent(runId)}/events?after=${latestSeq.current}`,
    );
    source.onopen = () => setState("live");
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
      // CONNECTING: the browser retries by itself. CLOSED: it gave up (e.g. 401 or 404).
      setState(source.readyState === EventSource.CLOSED ? "error" : "reconnecting");
    };

    return () => {
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
    };
  }, [runId, attempt]);

  const reconnect = useCallback(() => setAttempt((value) => value + 1), []);

  return { events, state, reconnect };
}

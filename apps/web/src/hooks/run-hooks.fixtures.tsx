/**
 * Test-only: runs the run hooks against a fake API. Requests go through the generated client to
 * a fetch mock (as in approval-panel.test.tsx), and live events come from a fake EventSource the
 * test drives (jsdom has none).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import type { RunEvent } from "@/lib/run-events";

/** Node's Request needs an absolute URL; the browser resolves "/api/v1/..." itself. */
export const BASE_URL = "http://localhost:8080";

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Answers one request; `path` is the URL path, such as "/api/v1/runs/<id>". */
export type ApiHandler = (request: Request, path: string) => Response | Promise<Response>;

/** Sends the generated client's requests to `handler` (call it in beforeEach). */
export function mockApi(handler: ApiHandler) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const request = input instanceof Request ? input : new Request(input);
    return handler(request, new URL(request.url).pathname);
  });
  configureApiClient();
  client.setConfig({ baseUrl: BASE_URL, fetch: fetchMock });
  return fetchMock;
}

/** The requests a fetch mock received, as "METHOD /path?query". */
export function requestsOf(fetchMock: ReturnType<typeof mockApi>): string[] {
  return fetchMock.mock.calls.map(([input]) => {
    const request = input as Request;
    const url = new URL(request.url);
    return `${request.method} ${url.pathname}${url.search}`;
  });
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

/** renderHook inside a QueryClientProvider; returns the client too. */
export function renderWithQuery<Props, Result>(
  hook: (props: Props) => Result,
  options: { initialProps?: Props; queryClient?: QueryClient } = {},
) {
  const queryClient = options.queryClient ?? makeQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const view = renderHook(hook, { wrapper, initialProps: options.initialProps as Props });
  return { ...view, queryClient };
}

/** An EventSource the test drives: `open()`, `send(...events)`, `end()`. */
export class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readonly url: string;
  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((message: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  private readonly listeners = new Map<string, Array<() => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  /** The newest stream the code under test opened. */
  static latest(): FakeEventSource {
    const source = FakeEventSource.instances.at(-1);
    if (!source) {
      throw new Error("No EventSource was opened");
    }
    return source;
  }

  addEventListener(type: string, listener: () => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.readyState = FakeEventSource.CLOSED;
  }

  open(): void {
    this.readyState = FakeEventSource.OPEN;
    this.onopen?.();
  }

  /** One SSE message per event, as the API sends them. */
  send(...events: RunEvent[]): void {
    for (const event of events) {
      this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(event) }));
    }
  }

  /** The API's `end` event after a finished run has replayed everything. */
  end(): void {
    for (const listener of this.listeners.get("end") ?? []) {
      listener();
    }
  }
}

/** Replaces the browser's EventSource for one test file (call it in beforeEach). */
export function installEventSource(): void {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
}

let eventSeq = 0;

/** A run event with the next seq (or the given one). */
export function runEvent(
  type: string,
  payload: Record<string, unknown> = {},
  seq: number = ++eventSeq,
): RunEvent {
  eventSeq = Math.max(eventSeq, seq);
  return { seq, type, payload, created_at: "2026-10-30T01:00:00+00:00" };
}

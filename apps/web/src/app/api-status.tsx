"use client";

import { useEffect, useState } from "react";

type Health = { status: string; version: string; environment: string };

type State =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

/** Calls the API through the same origin (Caddy routes /api/v1/* to FastAPI). */
export function ApiStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/health", { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        setState({ kind: "ok", health: (await response.json()) as Health });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            kind: "error",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => controller.abort();
  }, []);

  if (state.kind === "loading") {
    return <p className="status">API: checking…</p>;
  }
  if (state.kind === "error") {
    return (
      <p className="status status-error">
        API: unreachable ({state.message}). Open the app through the proxy at http://localhost:8080.
      </p>
    );
  }
  return (
    <p className="status status-ok">
      API: {state.health.status} · v{state.health.version} · {state.health.environment}
    </p>
  );
}

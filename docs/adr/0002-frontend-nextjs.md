# ADR 0002 — Next.js + shadcn/ui front end replaces Streamlit

- Status: accepted (2026-10-30)

## Context
The Streamlit UI ran the pipeline inside the page process. Every browser tab shared one queue
and event, the whole page reran every 0.3 s, and there was no login. We need:
- multi-user pages with live progress;
- approval panels with diffs and edits;
- paper and PDF views and training charts;
- Korean and English.

## Decision
- **Next.js 16.4** (App Router, `output: "standalone"`) + React 19.3 + TypeScript 6.0.
  TypeScript 7 (the Go compiler) has no compiler API yet, so we stay on 6.0.
- **shadcn/ui on Base UI** + Tailwind 4.3. TanStack Query 5 for server data, with a typed client
  generated from FastAPI's OpenAPI by Hey API (exact pin). Zustand only for UI state.
- **Live updates use typed SSE** from FastAPI with `Last-Event-ID` replay. Event names follow
  AG-UI, so a CopilotKit chat panel can be added later. AG-UI's own transport cannot resume a
  dropped stream, so we don't use it.
- **next-intl 4** with `en` and `ko` messages. API errors and events are message *codes*.
- Pages are client components fed by TanStack Query. Server code in Next.js is limited to
  Better Auth and layout.

## Consequences
- Caddy routes `/api/v1/*` straight to FastAPI. Next rewrites can buffer SSE, so they are never
  used for the API.
- Next.js has monthly security releases. React2Shell (CVE-2025-55182) was an unauthenticated RCE
  in App Router, so Renovate opens patch updates automatically and CI rebuilds images.
- One Node runtime in production (the `web` container).

## Alternatives considered
- **Vite + TanStack Router SPA**: no Node server in production. The runner-up; rejected because
  Better Auth and next-intl plug straight into Next.js.
- **SvelteKit / Nuxt**: the agent-UI ecosystem (shadcn, CopilotKit) is React-first.

import { ApiStatus } from "./api-status";

export default function HomePage() {
  return (
    <main className="shell">
      <h1>Agentic Research Platform</h1>
      <p className="muted">v2 · Phase 0 foundations</p>
      <ApiStatus />
    </main>
  );
}

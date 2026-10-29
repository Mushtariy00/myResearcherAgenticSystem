import { defineConfig } from "@hey-api/openapi-ts";

// Typed API client generated from FastAPI's OpenAPI document (`pnpm gen:openapi` refreshes it).
// Regenerate with `pnpm --filter @agentic/web gen:client`. Never edit src/client by hand.
export default defineConfig({
  input: "./openapi.json",
  output: "./src/client",
  plugins: [
    "@hey-api/client-fetch",
    "@hey-api/typescript",
    "@hey-api/sdk",
    "@tanstack/react-query",
  ],
});

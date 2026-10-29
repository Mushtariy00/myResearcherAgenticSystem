import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    // Pure logic runs in Node; component tests opt into jsdom with a file comment.
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

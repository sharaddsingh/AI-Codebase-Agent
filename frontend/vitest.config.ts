import { defineConfig } from "vitest/config";

// Vitest is intentionally kept out of the `next build` path: it has its own
// config here and only picks up `lib/**/*.test.ts` (pure-function tests).
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});

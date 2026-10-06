import { defineConfig } from "vitest/config";

export default defineConfig({
  // Vite reads the "@/*" alias from tsconfig.json itself.
  resolve: { tsconfigPaths: true },
  test: {
    // The logic under lib/ is plain TypeScript: no DOM, no React.
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});

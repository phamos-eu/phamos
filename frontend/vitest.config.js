import { defineConfig } from "vitest/config"
import path from "path"

// Unit tests for pure helpers shared by all cockpits (spa_shared) and this app.
// Component tests are out of scope; keep tested modules free of DOM/Vue imports.
export default defineConfig({
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
			"@spa": path.resolve(__dirname, "../spa_shared"),
		},
	},
	test: {
		include: ["../spa_shared/**/*.test.js", "src/**/*.test.js"],
		environment: "node",
		// Globals so test files outside this package need no `vitest` import to resolve.
		globals: true,
	},
})

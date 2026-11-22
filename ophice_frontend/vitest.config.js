import { defineConfig } from "vitest/config"
import path from "path"

// Unit tests for Ophice's pure helpers (#2089). Keep tested modules free of DOM/Vue imports.
export default defineConfig({
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
			"@spa": path.resolve(__dirname, "../spa_shared"),
		},
	},
	test: {
		include: ["src/**/*.test.js"],
		environment: "node",
	},
})

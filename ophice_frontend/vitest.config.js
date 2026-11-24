import { defineConfig } from "vitest/config"
import vue from "@vitejs/plugin-vue"
import path from "path"

// Unit tests for Ophice's pure helpers (#2089), plus setup checks of single components that run
// their <script setup> without a DOM (the window bits they touch are stubbed in the test).
export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
			"@spa": path.resolve(__dirname, "../spa_shared"),
		},
	},
	test: {
		include: ["src/**/*.test.js"],
		environment: "node",
		// Component tests: the client build of the .vue file, still without a DOM. A docblock
		// (`@vitest-environment`) would not switch the build in Vitest 2. Vitest 3 deprecates
		// environmentMatchGlobs (use test.projects then); Vitest 4 removes it.
		environmentMatchGlobs: [["src/components/**/*.test.js", "./src/test/nodeClientEnvironment.js"]],
	},
})

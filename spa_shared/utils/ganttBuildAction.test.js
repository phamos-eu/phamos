// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { ganttBuildAction } from "./ganttBuildAction.js"

describe("gantt build action", () => {
	it("never creates a chart without tasks (frappe-gantt throws on an empty list)", () => {
		expect(ganttBuildAction(false, 0)).toBe("clear")
	})

	it("clears an existing chart when the list becomes empty", () => {
		expect(ganttBuildAction(true, 0)).toBe("clear")
	})

	it("creates the chart for the first task", () => {
		expect(ganttBuildAction(false, 1)).toBe("create")
	})

	it("updates an existing chart in place", () => {
		expect(ganttBuildAction(true, 3)).toBe("update")
	})
})

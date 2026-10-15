// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { compareTodos, matchesTodo, sortTodos, todoPriorityTheme } from "./todoSort.js"

const todo = (name, date, priority, creation = "2026-01-01 10:00:00") => ({ name, date, priority, creation })

describe("ToDo order", () => {
	it("puts earlier due dates first and undated ToDos last", () => {
		const sorted = sortTodos([todo("none", null, "High"), todo("later", "2026-10-20", "Low"), todo("soon", "2026-10-15", "Low")])
		expect(sorted.map((t) => t.name)).toEqual(["soon", "later", "none"])
	})

	it("orders the same date by priority, then by age", () => {
		const sorted = sortTodos([
			todo("low", "2026-10-15", "Low"),
			todo("high-new", "2026-10-15", "High", "2026-03-01 10:00:00"),
			todo("medium", "2026-10-15", "Medium"),
			todo("high-old", "2026-10-15", "High", "2026-02-01 10:00:00"),
		])
		expect(sorted.map((t) => t.name)).toEqual(["high-old", "high-new", "medium", "low"])
	})

	it("does not change the input array", () => {
		const input = [todo("b", "2026-10-20", "High"), todo("a", "2026-10-15", "High")]
		sortTodos(input)
		expect(input.map((t) => t.name)).toEqual(["b", "a"])
		expect(compareTodos(input[1], input[0])).toBeLessThan(0)
	})
})

describe("ToDo search and badges", () => {
	const row = { name: "TD-1", summary: "Call Anna", reference_type: "Lead", reference_title: "ACME GmbH" }

	it("finds by text, reference type and reference title", () => {
		expect(matchesTodo(row, "anna")).toBe(true)
		expect(matchesTodo(row, "lead")).toBe(true)
		expect(matchesTodo(row, "acme")).toBe(true)
		expect(matchesTodo(row, "invoice")).toBe(false)
		expect(matchesTodo(row, "  ")).toBe(true)
	})

	it("colours priorities like the Issue list", () => {
		expect(todoPriorityTheme("High")).toBe("red")
		expect(todoPriorityTheme("Medium")).toBe("orange")
		expect(todoPriorityTheme("Low")).toBe("gray")
	})
})

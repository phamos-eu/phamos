// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { ageLabel, barHeight, formatComparison, formatDays, netLabel, pluralize } from "./dashboardFormat.js"

describe("comparison wording (unchanged from the checklist dashboard)", () => {
	it("formats percent points, days and levels", () => {
		expect(formatComparison(55, 50, "percent")).toBe("+5.0pp")
		expect(formatComparison(2.5, 4, "days")).toBe("-1.5d")
		expect(formatComparison(7, 9, "level")).toBe("-2")
	})

	it("formats relative change, new and no change", () => {
		expect(formatComparison(15, 10)).toBe("+50%")
		expect(formatComparison(5, 10)).toBe("-50%")
		expect(formatComparison(3, 0)).toBe("New")
		expect(formatComparison(0, 0)).toBe("No change")
		expect(formatComparison(null, 3)).toBe("No comparison")
	})
})

describe("small formatters", () => {
	it("keeps small bars visible", () => {
		expect(barHeight(0, 10)).toBe(0)
		expect(barHeight(1, 100)).toBe(4)
		expect(barHeight(5, 10)).toBe(50)
	})

	it("pluralises and labels ages", () => {
		expect(pluralize(1, "day", "days")).toBe("1 day")
		expect(ageLabel(0)).toBe("today")
		expect(ageLabel(12)).toBe("12 days")
		expect(formatDays(2.04)).toBe("2 days")
		expect(formatDays(1)).toBe("1 day")
		expect(formatDays(null)).toBe("—")
	})

	it("signs the backlog change", () => {
		expect(netLabel(2)).toBe("+2")
		expect(netLabel(-1)).toBe("-1")
		expect(netLabel(0)).toBe("±0")
	})
})

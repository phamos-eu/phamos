// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { billablePreset, ratingOptions, VALUE_ADD_DEFAULT } from "./timesheetRating.js"

// Value Add next to Percent Billable in the Personal Cockpit dialogs (#1743, parent #1031).
describe("timesheet rating", () => {
	it("offers 100 to 0 in steps of 25 and presets Value Add to 100", () => {
		expect(ratingOptions().map((row) => row.value)).toEqual(["100", "75", "50", "25", "0"])
		expect(ratingOptions()[0].label).toBe("100 %")
		expect(VALUE_ADD_DEFAULT).toBe("100")
	})

	it("presets Percent Billable from the project, 100 when it has none", () => {
		expect(billablePreset("50")).toBe("50")
		expect(billablePreset("0")).toBe("0")
		expect(billablePreset(0)).toBe("0")
		expect(billablePreset("")).toBe("100")
		expect(billablePreset(null)).toBe("100")
	})
})

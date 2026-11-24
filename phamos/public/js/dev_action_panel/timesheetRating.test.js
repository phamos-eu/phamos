import { describe, expect, it } from "vitest"
import { PERCENT_BILLABLE_DEFAULT, percentBillablePreset, RATING_OPTIONS } from "./timesheetRating.js"

describe("timesheetRating", () => {
	it("offers 100 to 0 in steps of 25", () => {
		expect(RATING_OPTIONS).toEqual([100, 75, 50, 25, 0])
	})

	it("starts Percent Billable at 0 in the stop and break dialogs when there is no preset", () => {
		expect(PERCENT_BILLABLE_DEFAULT).toBe(0)
		for (const missing of [undefined, null, "", "abc", "33"]) expect(percentBillablePreset(missing)).toBe(0)
	})

	it("starts Percent Billable at the project's preset: 100 for customer projects (#1896)", () => {
		expect(percentBillablePreset("100")).toBe(100)
		expect(percentBillablePreset("50")).toBe(50)
		expect(percentBillablePreset("0")).toBe(0)
		expect(percentBillablePreset(75)).toBe(75)
	})
})

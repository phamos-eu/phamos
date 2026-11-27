import { describe, expect, it } from "vitest"
import {
	PERCENT_BILLABLE_DEFAULT,
	percentBillablePreset,
	RATING_OPTIONS,
	ratingArgs,
	VALUE_ADD_DEFAULT,
} from "./timesheetRating.js"

// Value Add next to Percent Billable in the Dev and Sales Action Panels (#1744, parent #1031).
describe("timesheetRating", () => {
	it("offers 100 to 0 in steps of 25 and presets Value Add to 100", () => {
		expect(RATING_OPTIONS).toEqual([100, 75, 50, 25, 0])
		expect(VALUE_ADD_DEFAULT).toBe(100)
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

	it("sends Value Add and Percent Billable", () => {
		expect(ratingArgs(25, 50)).toEqual({ value_add: 25, percent_billable: 50 })
		expect(ratingArgs(0, 0)).toEqual({ value_add: 0, percent_billable: 0 })
	})
})

import { describe, expect, it } from "vitest"
import { PERCENT_BILLABLE_DEFAULT, RATING_OPTIONS, ratingArgs, VALUE_ADD_DEFAULT } from "./timesheetRating.js"

// Value Add next to Percent Billable in the Dev and Sales Action Panels (#1744, parent #1031).
describe("timesheetRating", () => {
	it("offers 100 to 0 in steps of 25 and presets Value Add to 100", () => {
		expect(RATING_OPTIONS).toEqual([100, 75, 50, 25, 0])
		expect(VALUE_ADD_DEFAULT).toBe(100)
	})

	it("starts Percent Billable at 0 in the stop and break dialogs", () => {
		expect(PERCENT_BILLABLE_DEFAULT).toBe(0)
	})

	it("sends Value Add and Percent Billable", () => {
		expect(ratingArgs(25, 50)).toEqual({ value_add: 25, percent_billable: 50 })
		expect(ratingArgs(0, 0)).toEqual({ value_add: 0, percent_billable: 0 })
	})
})

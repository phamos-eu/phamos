import { describe, expect, it } from "vitest"
import { billablePreset, RATING_OPTIONS, ratingArgs, showBillable, VALUE_ADD_DEFAULT } from "./timesheetRating.js"

// Value Add next to Percent Billable in the Dev and Sales Action Panels (#1744, parent #1031).
describe("timesheetRating", () => {
	it("offers 100 to 0 in steps of 25 and presets Value Add to 100", () => {
		expect(RATING_OPTIONS).toEqual([100, 75, 50, 25, 0])
		expect(VALUE_ADD_DEFAULT).toBe(100)
	})

	it("shows Percent Billable only for billable projects", () => {
		expect(showBillable({ is_billable: true })).toBe(true)
		expect(showBillable({ is_billable: false })).toBe(false)
		expect(showBillable({ project_is_billable: true })).toBe(true)
		expect(showBillable(null)).toBe(false)
	})

	it("presets Percent Billable from the project, 100 when the project has none", () => {
		expect(billablePreset({ is_billable: true, percent_billable: "50" })).toBe(50)
		expect(billablePreset({ is_billable: true, percent_billable: "0" })).toBe(0)
		expect(billablePreset({ is_billable: true, percent_billable: "" })).toBe(100)
		expect(billablePreset({ project_is_billable: true, project_percent_billable: "75" })).toBe(75)
		expect(billablePreset({ is_billable: false, percent_billable: "75" })).toBe(0)
	})

	it("sends Value Add always and Percent Billable only when it was shown", () => {
		expect(ratingArgs(25, 50)).toEqual({ value_add: 25, percent_billable: 50 })
		expect(ratingArgs(75, null)).toEqual({ value_add: 75 })
		expect(ratingArgs(0, 0)).toEqual({ value_add: 0, percent_billable: 0 })
	})
})

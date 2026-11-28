import { describe, expect, it } from "vitest"
import { blankOpenMonths, isOpenMonth } from "./open_months"

const TODAY = "2026-11-27"

describe("isOpenMonth", () => {
	it("is false for past months and the current month", () => {
		expect(isOpenMonth("2026-10", TODAY)).toBe(false)
		expect(isOpenMonth("2026-11", TODAY)).toBe(false)
	})

	it("is true for months after the current month, also across a year", () => {
		expect(isOpenMonth("2026-12", TODAY)).toBe(true)
		expect(isOpenMonth("2027-01", TODAY)).toBe(true)
	})
})

describe("blankOpenMonths", () => {
	it("keeps real zeros up to the current month and blanks the months after it", () => {
		const months = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01"]
		expect(blankOpenMonths([5, 0, 3, 0, 0], months, TODAY)).toEqual([5, 0, 3, null, null])
	})

	it("blanks nothing when the range ends before today", () => {
		expect(blankOpenMonths([1, 0], ["2026-05", "2026-06"], TODAY)).toEqual([1, 0])
	})

	it("blanks everything when the range starts after today", () => {
		expect(blankOpenMonths([0, 0], ["2027-02", "2027-03"], TODAY)).toEqual([null, null])
	})
})

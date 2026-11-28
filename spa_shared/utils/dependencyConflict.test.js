import { describe, expect, it } from "vitest"
import { startsBeforePredecessorEnds, taskEndDay } from "./dependencyConflict.js"

const pred = { exp_start_date: "2026-11-10", exp_end_date: "2026-11-20" }

describe("startsBeforePredecessorEnds", () => {
	it("is a conflict when the successor starts a day before the predecessor ends", () => {
		expect(startsBeforePredecessorEnds(pred, { exp_start_date: "2026-11-19" })).toBe(true)
	})

	it("is fine on the same day and later", () => {
		expect(startsBeforePredecessorEnds(pred, { exp_start_date: "2026-11-20" })).toBe(false)
		expect(startsBeforePredecessorEnds(pred, { exp_start_date: "2026-11-21" })).toBe(false)
	})

	it("is no conflict when a date is missing", () => {
		expect(startsBeforePredecessorEnds(pred, {})).toBe(false)
		expect(startsBeforePredecessorEnds({}, { exp_start_date: "2026-11-01" })).toBe(false)
	})

	it("takes the start as the end of a predecessor without an end, like its bar", () => {
		const oneDay = { exp_start_date: "2026-11-20" }
		expect(taskEndDay(oneDay)).toBe("2026-11-20")
		expect(startsBeforePredecessorEnds(oneDay, { exp_start_date: "2026-11-19" })).toBe(true)
	})

	it("ignores the time part of datetimes", () => {
		expect(
			startsBeforePredecessorEnds(
				{ exp_end_date: "2026-11-20 00:00:00" },
				{ exp_start_date: "2026-11-20 09:00:00" }
			)
		).toBe(false)
	})
})
